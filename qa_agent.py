from telethon import TelegramClient, Button
import asyncio
import csv
import time
import os
import pdfplumber

API_ID = 24580235
API_HASH = "7644a557e5c5149a4dc6bae8b4ff04f"
BOT_USERNAME = 'Accurate_data_analysis_bot'
SESSION = "testsession"
TEST_FILE = "Kopio_ Kopio_ BA Аналитика по всем записям.xlsx"
PROMPT_FILE = "prompts.txt"
OUTFILE = "qa_results.csv"
LOGFILE = "qa_log_all_messages.csv"

if not os.path.exists(LOGFILE):
    with open(LOGFILE, "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "from_bot", "message_text"])

async def wait_for_message(client, substr, limit=12, timeout=30):
    import telethon
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            async for msg in client.iter_messages(BOT_USERNAME, limit=limit):
                try:
                    if getattr(msg, "text", None) and substr in msg.text:
                        with open(LOGFILE, "a", newline='', encoding='utf-8') as f:
                            writer = csv.writer(f)
                            writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), True, msg.text])
                        return msg
                except Exception as inner_e:
                    print(f"[warn] Skipping message: {inner_e}")
                    continue
        except telethon.errors.common.TypeNotFoundError as e:
            print(f"[warn] TypeNotFoundError, skipping chunk: {e}")
            continue
        except Exception as e:
            print(f"[warn] General error: {e}")
            continue
        await asyncio.sleep(1)
    return None

async def extract_pdf_text_from_msg(client, msg):
    # Download file to temp location
    if not msg.document or not msg.file:
        return None
    filename = "temp_answer.pdf"
    await msg.download_media(file=filename)
    text = ""
    with pdfplumber.open(filename) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    os.remove(filename)
    return text.strip()

async def main():
    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    print("Signed in!")
    await client.send_message(BOT_USERNAME, "/start")
    await asyncio.sleep(2)
    await client.send_file(BOT_USERNAME, TEST_FILE)
    print("Uploaded file, waiting for bot to respond with buttons...")
    await asyncio.sleep(10)

    prompts = [l.strip() for l in open(PROMPT_FILE, encoding='utf-8') if l.strip()]

    with open(OUTFILE, "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["prompt", "response"])

        for idx, prompt in enumerate(prompts):
            found_expert = False
            for _ in range(10):
                messages = [msg async for msg in client.iter_messages(BOT_USERNAME, limit=8)]
                messages.sort(key=lambda m: m.id, reverse=True)
                for msg in messages:
                    if msg.buttons:
                        for row in msg.buttons:
                            for button in row:
                                if "Expert mode" in button.text or "Экспертный режим" in button.text:
                                    try:
                                        await msg.click(text=button.text)
                                        found_expert = True
                                        print(f"[{idx+1}/{len(prompts)}] Pressed Expert mode.")
                                        with open(LOGFILE, "a", newline='', encoding='utf-8') as logf:
                                            log_writer = csv.writer(logf)
                                            log_writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), True, f"Clicked button: {button.text}"])
                                        break
                                    except Exception as e:
                                        print(f"Error clicking button: {e}")
                            if found_expert:
                                break
                    if found_expert:
                        break
                if found_expert:
                    break
                await asyncio.sleep(1)
            if not found_expert:
                print("Could not find Expert mode button, skipping this prompt.")
                writer.writerow([prompt, "NO EXPERT MODE BUTTON"])
                continue

            ok = False
            for _ in range(15):
                msg = await wait_for_message(client, "Expert mode:")
                if msg:
                    ok = True
                    break
                await asyncio.sleep(1)
            if not ok:
                print("No prompt for expert request, skipping.")
                writer.writerow([prompt, "NO PROMPT FROM BOT"])
                continue

            await client.send_message(BOT_USERNAME, prompt)
            print(f"[{idx+1}/{len(prompts)}] Sent prompt: {prompt}")
            with open(LOGFILE, "a", newline='', encoding='utf-8') as logf:
                log_writer = csv.writer(logf)
                log_writer.writerow([time.strftime('%Y-%m-%d %H:%M:%S'), False, prompt])

            await asyncio.sleep(7)

            response = None
            for _ in range(12):
                async for msg in client.iter_messages(BOT_USERNAME, limit=6):
                    # Handle PDF answer
                    if msg.document and getattr(msg.document, 'mime_type', None) == 'application/pdf':
                        pdf_text = await extract_pdf_text_from_msg(client, msg)
                        if pdf_text:
                            response = pdf_text
                            break
                    # Handle plain text answer
                    elif (
                        msg.text
                        and prompt not in msg.text
                        and "File received" not in msg.text
                        and "Choose an action" not in msg.text
                        and "Expert mode" not in msg.text
                        and "describe your request" not in msg.text
                    ):
                        response = msg.text
                        break
                if response:
                    break
                await asyncio.sleep(2)
            writer.writerow([prompt, response or "NO RESPONSE"])
            print(f"[{idx+1}/{len(prompts)}] Got response.")

if __name__ == "__main__":
    asyncio.run(main())

