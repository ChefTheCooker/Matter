content = open('D:/Matter/core/speaker.py', 'r').read()

new_func = '''def _speak_elevenlabs(text: str):
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import play
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE,
            text=text,
            model_id="eleven_monolingual_v1",
            output_format="mp3_44100_128",
        )
        play(audio)
    except Exception as e:
        if ENABLE_LOGS:
            print(f"[Speaker] ElevenLabs error: {e}. Falling back to pyttsx3.")
        _speak_pyttsx3(text)'''

import re
content = re.sub(
    r'def _speak_elevenlabs\(text: str\):.*?_speak_pyttsx3\(text\)',
    new_func,
    content,
    flags=re.DOTALL
)

open('D:/Matter/core/speaker.py', 'w').write(content)
print("Done")