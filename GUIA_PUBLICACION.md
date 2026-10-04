# Guía para publicar y arrancar (paso a paso)

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Pasos que solo puedes dar tú. Todos los comandos son para **PowerShell**, desde
`C:\Users\alber\OneDrive\Escritorio\cuaderno-bot`. Hazlos en este orden: el
pre-registro (paso 6) va **después** de dejar listas la firma y la web, y
**antes** del día 0.

## 1. Email público de los commits

El historial todavía no se ha publicado, así que ahora se puede cambiar sin
reescribir nada público.

1. GitHub → *Settings* → *Emails* → activa **Keep my email addresses private** y
   copia tu dirección `NÚMERO+usuario@users.noreply.github.com`.
2. Pásamela y reescribo el autor de los commits locales, o hazlo tú:

```powershell
git config user.email "NÚMERO+usuario@users.noreply.github.com"
```

```powershell
git rebase -r --root --exec "git commit --amend --no-edit --reset-author"
```

## 2. Clave de firma (SSH)

```powershell
ssh-keygen -t ed25519 -C "firma cuaderno-bot" -f "$env:USERPROFILE\.ssh\firma_cuaderno"
```

```powershell
git config gpg.format ssh
git config user.signingkey "$env:USERPROFILE\.ssh\firma_cuaderno.pub"
git config commit.gpgsign true
git config tag.gpgsign true
```

En GitHub → *Settings* → *SSH and GPG keys* → **New SSH key** → tipo **Signing
Key** → pega el contenido de `firma_cuaderno.pub`.

Para firmar también los commits que ya existen (el historial sigue sin publicar):

```powershell
git rebase -r --root --exec "git commit --amend --no-edit -S"
```

## 3. Repositorio público

1. GitHub → **New repository** → nombre `cuaderno-bot` → **Public** → sin README
   (ya lo tenemos).
2. Súbelo:

```powershell
git remote add origin https://github.com/TU_USUARIO/cuaderno-bot.git
git push -u origin main
```

## 4. Protección de la rama y de los tags

GitHub → repositorio → *Settings* → *Rules* → *Rulesets* → **New branch ruleset**:
- Target: *Default branch*.
- Activa **Restrict deletions**, **Block force pushes** y **Require signed commits**.
- **No** actives "Require a pull request": el bot sube directamente.

Otro **New tag ruleset** con el patrón `v*`: **Restrict updates** y **Restrict
deletions** (nadie podrá mover ni borrar el tag del pre-registro).

Los commits del bot se crean con la API de GitHub (`scripts/commit_firmado.py`),
que según la documentación de GitHub los marca como verificados. Si en el día 0
el commit del bot **no** aparece como *Verified*, avísame antes de seguir: con
"Require signed commits" activado, el bot no podría subir nada.

## 5. GitHub Actions y Pages

- *Settings* → *Actions* → *General*: deja Actions activadas.
- *Settings* → *Pages* → *Source*: **GitHub Actions** (la web se despliega desde
  el workflow; Fase 7).

## 6. Pre-registro (día 0, una sola vez)

Con el árbol limpio y todo subido:

```powershell
.venv\Scripts\python scripts\preregistro.py
```

Te muestra el SHA-256 y el texto del tuit del día 0. Después:

```powershell
git add PREREGISTRO.md PREREGISTRO.md.sha256
git commit -m "Pre-registro: día 0"
git tag -s v1.0-preregistro -m "Pre-registro del experimento de 90 días"
git push
git push origin v1.0-preregistro
```

**Sello opcional en Bitcoin:** en https://opentimestamps.org arrastra
`PREREGISTRO.md`, descarga el `.ots` y súbelo con un commit (el cliente de
línea de comandos no funciona en Windows; en el servidor de Actions sí).

## 7. Tuit del día 0

Publica a mano el texto que dio el paso 6. El tuit no lleva enlaces; el enlace
al repositorio va en un comentario. La hora de publicación en X es el segundo
ancla: quien administra el repositorio podría reescribir el historial de git,
pero no el de X.

## 8. Inicializar (día 0)

GitHub → *Actions* → **Paper trading diario** → *Run workflow* → marca
**inicializar** → *Run*. Crea el archivo de velas y el evento `inicio`, con el
hash de la configuración congelada. Comprueba que el commit del bot sale como
**Verified**.

## 9. Día 1 en adelante

Automático cada día a las **00:17 UTC** (02:17 en Madrid en horario de verano y
01:17 en invierno), con reintento a las 02:47 UTC. Cada día te dejo el texto, la
imagen y el hash para publicar (Fase 6).

## Dónde se ejecuta: GitHub Actions frente a un VPS

| | GitHub Actions (elegido) | VPS pequeño (unos 4-6 €/mes) |
|---|---|---|
| Coste | Gratis en repositorios públicos | De pago |
| Transparencia | Registros de ejecución públicos junto al código | Registros privados |
| Mantenimiento | Ninguno | Sistema, seguridad, copias |
| Puntualidad | Retrasos posibles en horas punta, y alguna ejecución puede perderse | Exacta |
| Riesgos | Cron desactivado tras 60 días sin actividad (los commits diarios lo evitan) | Caída del servidor, claves en la máquina |

Los retrasos no afectan a las cuentas: la decisión usa la vela ya cerrada y la
ejecución, la apertura de la vela en curso, sea cual sea la hora de la
ejecución. Una ejecución perdida queda como vela perdida, visible en el panel.
