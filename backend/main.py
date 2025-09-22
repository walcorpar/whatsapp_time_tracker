from fastapi import FastAPI, HTTPException
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
from twilio.request_validator import RequestValidator
from twilio.rest import Client
import smtplib
from email.mime.text import MIMEText

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

app = FastAPI()

# Configuración de CORS (opcional, si usas frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Validar solicitud de Twilio
def validate_twilio_request(request_body, signature, url):
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(url, request_body, signature)

# Enviar correo
def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_USER
    msg['To'] = to_email

    with smtplib.SMTP('smtp.gmail.com', 587) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)

# Endpoint para recibir mensajes de WhatsApp
@app.post("/whatsapp")
async def handle_whatsapp_message(
    From: str,
    Body: str,
    Signature: str = None
):
    # Validar solicitud (opcional, para seguridad)
    url = "https://tu-app.onrender.com/whatsapp"  # Ajusta con tu URL de Render
    if not validate_twilio_request(str({"From": From, "Body": Body}), Signature, url):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # Procesar el mensaje
    phone_number = From.replace("whatsapp:", "")  # Extraer número
    parts = Body.strip().lower().split()
    command = parts[0] if parts else ""

    if command == "entrada":
        if len(parts) < 2:
            return {"message": "Envía 'entrada gps' con coordenadas (lat,long)"}
        try:
            gps_position = parts[1]  # Ejemplo: "-33.4521,-70.6536"
            entry = {
                "phone_number": phone_number,
                "entry_time": datetime.utcnow(),
                "gps_position": gps_position,
                "exit_time": None
            }
            result = db.entries.insert_one(entry)
            inserted_entry = db.entries.find_one({"_id": result.inserted_id})
            inserted_entry["_id"] = str(inserted_entry["_id"])

            # Enviar correo de notificación
            admin_email = "admin@example.com"  # Ajusta el email del admin
            subject = f"Nueva Entrada - {phone_number}"
            body = f"Entrada registrada:\n- Teléfono: {phone_number}\n- Hora: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n- GPS: {gps_position}"
            send_email(admin_email, subject, body)

            # Responder por WhatsApp
            twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            twilio_client.messages.create(
                from_=TWILIO_WHATSAPP_NUMBER,
                to=From,
                body=f"WZP! Entrada registrada a las {datetime.utcnow().strftime('%H:%M')} en {gps_position} 😎"
            )

            return {"message": "Entrada registrada", "entry": inserted_entry}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error: {str(e)}")

    elif command == "salida":
        active_entry = db.entries.find_one({"phone_number": phone_number, "exit_time": None})
        if not active_entry:
            return {"message": "No hay entrada activa para registrar salida"}
        update = {"$set": {"exit_time": datetime.utcnow()}}
        db.entries.update_one({"_id": active_entry["_id"]}, update)
        return {"message": "Salida registrada"}

    return {"message": "Envía 'entrada gps' o 'salida'"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)