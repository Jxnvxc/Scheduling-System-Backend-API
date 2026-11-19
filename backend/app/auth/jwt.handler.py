from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.config import settings


def create_AccesToken(data: dict):#Purpose: Gumagawa ng bagong token. Tatanggapin niya yung data (isang dictionary na may laman tulad ng {"sub": "maria@example.com", "role": "admin"}).
  toEncode = data.copy() #Purpose: Kinokopya niya yung data mo. Bakit kailangang kopyahin? Para hindi mabago yung original na data mo sa labas ng function na 'to. (Safe coding practice).

  Expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES) #Purpose: Kinukuha niya yung kasalukuyang oras at nagdadagdag ng expiration time (galing sa settings). Ito yung magiging expiration ng token mo.

  toEncode.update({"Exp": Expire}) #Purpose: Dinadagdag niya yung expiration time sa dictionary na 'toEncode'. Ngayon, may expiration na yung token mo.

  Encoded_jwt = jwt.encode(toEncode, settings.JWT_SECRET, algorithm = settings.JWT_ALGORITHM) #Purpose: Ginagawa niya yung token gamit ang 'jose' library. Gamit ang secret key at algorithm na galing sa settings, nagiging encoded string yung data mo.

  return Encoded_jwt #Purpose: Ibinabalik niya yung encoded token. Ito yung token na gagamitin mo para sa authentication mo.

def VerifyAccess(token: str):
  try:
    Load = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])  
    return Load
  except JWTError:
    return None