import asyncio
import httpx
import json
import os
import re
from urllib.parse import parse_qs, unquote

HOST = os.environ.get("CHAR_DATA_HOST", "127.0.0.1")
PORT = int(os.environ.get("CHAR_DATA_PORT", "4568"))

async def get_char_data(char_name: str):
    """Fetches character data from the AQW character page."""
    try:
        url = f"https://www.aq.com/character.asp?id={char_name}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()

        html_content = response.text

        # The flashvars can be in a <param> tag or an <embed> tag.
        # Let's try to find it in either, using a regex for flexibility.
        match = re.search(r'flashvars="([^"]+)"', html_content, re.IGNORECASE)
        if not match:
            # Fallback for the <param name="FlashVars" ...> format
            match = re.search(r'<param name="FlashVars" value="([^"]+)"', html_content, re.IGNORECASE)

        if not match:
            if "is wandering in the Void" in html_content:
                return {"error": "Character is inactive or does not exist."}
            return {"error": "Could not find flashvars in the page. The page structure may have changed."}

        flash_vars_str = match.group(1)
        
        # The string is HTML-encoded (&amp;) and URL-encoded.
        decoded_vars = unquote(flash_vars_str.replace("&amp;", "&"))
        
        # The decoded string is like a query string, so we can parse it
        parsed_vars = parse_qs(decoded_vars)

        # Extracting specific data points
        # The values in parsed_vars are lists, so we take the first element
        data = {
            "name": parsed_vars.get("strName", [char_name])[0],
            "level": parsed_vars.get("intLevel", ["N/A"])[0],
            "class": parsed_vars.get("strClassName", ["N/A"])[0],
            "helm": parsed_vars.get("strHelmName", ["N/A"])[0],
            "armor": parsed_vars.get("strArmorName", ["N/A"])[0],
            "cape": parsed_vars.get("strCapeName", ["N/A"])[0],
            "weapon": parsed_vars.get("strWeaponName", ["N/A"])[0],
            "pet": parsed_vars.get("strPetName", ["N/A"])[0],
        }
        return data

    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error occurred: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"An unexpected error occurred: {str(e)}"}

async def handle_client(reader, writer):
    """Handles incoming client connections."""
    data = await reader.read(1024)
    message = data.decode().strip()
    addr = writer.get_extra_info('peername')
    print(f"Received '{message}' from {addr}")

    if not message:
        writer.close()
        await writer.wait_closed()
        return

    char_data = await get_char_data(message)
    
    response_data = json.dumps(char_data)
    
    writer.write(response_data.encode())
    await writer.drain()

    print(f"Sent data for '{message}'")
    writer.close()
    await writer.wait_closed()

async def main():
    """Starts the TCP server."""
    server = await asyncio.start_server(
        handle_client, HOST, PORT)

    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped.")
