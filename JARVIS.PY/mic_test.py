"""Explicit microphone capture diagnostic; importing never opens hardware.

Run ``python mic_test.py --help`` for device settings. No audio is saved or sent.
"""

import argparse

import speech_recognition as sr


def main(device_index=1, sample_rate=44100, chunk_size=1024):
    recognizer = sr.Recognizer()

    print("Opening microphone...")

    try:
        with sr.Microphone(
            device_index=device_index,
            sample_rate=sample_rate,
            chunk_size=chunk_size
        ) as source:
            print("Microphone opened successfully.")
            print("Calibrating...")

            recognizer.adjust_for_ambient_noise(source, duration=1)

            print("SAY: Hello Jarvis")

            recognizer.listen(source, timeout=5, phrase_time_limit=3)
    except sr.WaitTimeoutError:
        print("No speech detected before timeout. Try again when ready.")
        return 1
    except Exception as error:
        # Device errors can contain local paths or personal device names.
        print(f"Microphone diagnostic failed: {type(error).__name__}. Check device settings and permissions.")
        return 1

    print("Audio captured successfully!")
    return 0


def nonnegative_integer(value):
    try:
        parsed = int(value)
        if parsed >= 0:
            return parsed
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("expected a non-negative integer")


def positive_integer(value):
    parsed = nonnegative_integer(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def cli(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-index", type=nonnegative_integer, default=1)
    parser.add_argument("--sample-rate", type=positive_integer, default=44100)
    parser.add_argument("--chunk-size", type=positive_integer, default=1024)
    args = parser.parse_args(argv)
    return main(args.device_index, args.sample_rate, args.chunk_size)


if __name__ == "__main__":
    raise SystemExit(cli())
