### Easy Way: Docker

#### PRE-INSTALL REQUIREMENTS
- Registered domain name for external access
- Require SSL connection (Nginx/Caddy reverse proxy, Cloudflare Zero Trust Tunnel, Tailscale, Ngrok, etc.)

Note: This guide uses `docker compose`. Depending on your docker setup, you may need to use the command `docker-compose` instead.


#### COPY GITHUB REPOSITORY INTO A NEW DIRECTORY (PYFEDI/)
```bash
sudo git clone https://codeberg.org/rimu/pyfedi.git
cd pyfedi/
```

#### PREPARE DOCKER ENVIRONMENT FILE
```bash
sudo cp env.docker.sample .env.docker
sudo nano .env.docker
```
- `SECRET_KEY='...'` - Replace text with random numbers and letters. Should be at least 32 characters long.
- `SERVER_NAME='...'` - Enter a registered domain name (do **NOT** include `http://`). Use the address `127.0.0.1:8030` for testing or development.
<br>
Note: If your testing/dev instance needs to federate with other instances then you will **need** a domain name. Ngrok.com has a free tier you can use - get this before proceeding because changing the `SERVER_NAME` variable later involves wiping all data and starting again.
- Add additional variables (Mail, Cloudflare, etc.) relevant to your needs. See file `pyfedi/env.sample` for example variables.


#### CHECK COMPOSE.YML
- Check ports (8030:5000) and volume definitions if this is relevant to your needs. If not, skip this step.
```bash
sudo nano compose.yaml
```

#### CREATE REQUIRED FOLDERS WITH REQUIRED PERMISSIONS

Do **not** skip this. Enter your sudo password when prompted.

```bash
./docker-dirs.sh
```
This will automatically create the following directories with the required permissions to continue:
- pyfedi/pgdata/
- pyfedi/media/
- pyfedi/logs/
- pyfedi/tmp/

#### BUILD PIEFED
```bash
export DOCKER_BUILDKIT=1
sudo docker compose up --build
```
- Wait until text in terminal stops scrolling. Ignore the configuration check errors at this point.
- If you see many permission-related errors, try repeating the previous step (with the chown command using 1000 instead of your username)
- Test external access from browser (On port 8030). Watch for movement in terminal window. Browser will show "Internal Server Error" message. Proceed to initialize database to address this error message.

#### INITIALIZE DATABASE
- Open a new terminal window
```bash
sudo docker exec -it piefed_app1 sh
```

The above command will get you into a shell inside the container. Then, inside that shell run this:

```bash
export FLASK_APP=pyfedi.py
flask init-db
```
- Enter username, email (optional), and password.
- Test external access from browser again. PieFed should now load. Login as admin with the same username and password.
```bash
exit
```
- Close this terminal window

#### SHUT DOWN PIEFED & START AGAIN IN BACKGROUND
- Return to the main terminal window and press `CTRL+C` to temporarily shut down PieFed
- Start PieFed in the background:
```bash
sudo docker compose up -d
```

- During startup, you might see "Running configuration check..." followed by validation messages. Checkmarks (✅)
indicate successful configuration, warnings (⚠️) are usually fine to ignore, but X marks (❌) indicate critical issues that need fixing.

#### SETUP CRON (AUTOMATED) JOBS
```bash
sudo nano /etc/cron.d/piefed
```
- Copy & Paste the text below
- Replace `<USERNAME>` with account username
```
5 2 * * * <USERNAME> docker exec piefed_app1 bash -c "cd /app && ./daily.sh"
5 4 * * 1 <USERNAME> docker exec piefed_app1 bash -c "cd /app && ./remove_orphan_files.sh"
1 */6 * * * <USERNAME> docker exec piefed_app1 bash -c "cd /app && ./email_notifs.sh"
*/5 * * * * <USERNAME> docker exec piefed_app1 bash -c "cd /app && ./send_queue.sh"
```

#### UPDATING & RESTARTING PIEFED
Manually:
```bash
cd pyfedi/
sudo git pull
export DOCKER_BUILDKIT=1
sudo docker compose up -d --build
```
Provided script:
```bash
cd pyfedi/
./deploy-docker.sh
```
NOTE: Major version updates may require extra steps. Check [PieFed Meta](https://piefed.social/c/piefed_meta) for announcements and further instructions.

#### VIEW LOGS
```bash
sudo docker logs -f piefed_app1
```
- `-f` Option displays logs with constant updates. Press `CTRL+C` to exit.