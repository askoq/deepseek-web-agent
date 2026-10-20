# DeepSeek Web Agent

Turns the free [DeepSeek Web chat](https://chat.deepseek.com) into a coding agent: it can read, edit and create files in a folder on your computer and run terminal commands.

It's two parts:

- `bridge.py` runs on your computer and does the actual work (files, commands) inside the folder you choose.
- `deepseek-agent_user.js` is a userscript that adds an **Agent** switch to the DeepSeek chat and hands the model's tool calls to the bridge.

> Unofficial, independent project. It is NOT affiliated with, endorsed by or connected to DeepSeek or DeepSeek AI in any way. Use at your own risk.

## Installation

### 1. Python

Needs Python 3.10+. Get it from [python.org](https://www.python.org/downloads/) and on Windows tick **"Add python.exe to PATH"**.

### 2. Download this project

Click **Code -> Download ZIP** on GitHub and unpack it anywhere.

### 3. Start the bridge

On Windows, run `start_bridge.bat` in the project folder. On Linux / macOS, open a terminal there and run `bash start_bridge.sh`.

A console window opens. It shows the address the bridge runs on (`http://127.0.0.1:3456`), the current workspace folder and a long random token. Copy the token, you'll need it in a minute. Leave the window open: closing it stops the bridge.

### 4. Install a userscript manager

Add [Violentmonkey](https://violentmonkey.github.io/) (recommended) or [Tampermonkey](https://www.tampermonkey.net/) to your browser.

### 5. Add the script

1. Create a new script.
2. Delete the template text it fills in.
3. Open [`deepseek-agent_user.js`](deepseek-agent_user.js), copy everything and paste it in.
4. Save.

## Usage

1. Go to [chat.deepseek.com](https://chat.deepseek.com). You should see a new **Agent button** next to DeepThink and Search. Click it to turn it on.
2. Paste the token from the bridge window when it asks.
3. A folder button appears above the message box. Click it and pick your project folder.
4. Write what you want.

The model's actions show up as cards in the chat, and results go back to it automatically. Turn Agent off when you just want to chat normally.

The small `confirm` / `auto-run` label next to the folder name is the permission mode (click to switch):

- `confirm` (default): before anything that changes stuff (writing files, running commands, fetching web pages) you get an Allow / Deny card and nothing happens until you click. Reading and searching files don't ask.
- `auto-run`: no questions asked, everything just runs.

## Other

- Until you pick a folder, the agent works in `~/agent-workspace`. The folder you pick with the button is forgotten when the bridge restarts.
- File tools stay inside the workspace, but `run_command` doesn't: it has your full user permissions and no sandbox, so read what you're allowing.

## License

[MIT](LICENSE)
