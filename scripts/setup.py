"""Generate local secrets without overwriting existing configuration. Python stdlib only."""
import base64
import os
import secrets
from pathlib import Path
root=Path(__file__).resolve().parent.parent
target=root/'.env'
if target.exists():
    raise SystemExit('.env already exists; nothing changed.')
secret_names=['POSTGRES_PASSWORD','SECRET_KEY','SERVICE_TOKEN','ADMIN_PASSWORD','ARI_PASSWORD']
content=(root/'.env.example').read_text(encoding='utf-8')
for key in secret_names:
    content=content.replace(key+'=\n',key+'='+secrets.token_hex(32)+'\n')
content=content.replace('BACKUP_KEY=\n','BACKUP_KEY='+base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()+'\n')
with target.open('x',encoding='utf-8') as stream:
    stream.write(content)
os.chmod(target,0o600)
print('Created .env. Read ADMIN_PASSWORD locally. Store BACKUP_KEY separately and securely.')
