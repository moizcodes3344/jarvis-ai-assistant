import speech_recognition as sr

recognizer = sr.Recognizer()

print("Opening microphone...")

with sr.Microphone(
    device_index=1,
    sample_rate=44100,
    chunk_size=1024
) as source:
    print("Microphone opened successfully.")
    print("Calibrating...")

    recognizer.adjust_for_ambient_noise(source, duration=1)

    print("SAY: Hello Jarvis")

    audio = recognizer.listen(
        source,
        timeout=5,
        phrase_time_limit=3
    )

print("Audio captured successfully!")