# app/main.py

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import shutil
from pathlib import Path
import azure.cognitiveservices.speech as speechsdk
import openai
import os
import ffmpeg
import logging

# Load environment variables from .env file (ensure you have one with necessary variables)
load_dotenv()

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add CORS middleware (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve index.html at root
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("index.html not found.")
        return HTMLResponse(content="<h1>index.html not found.</h1>", status_code=404)

# Initialize Azure and OpenAI credentials
speech_key = os.getenv('AZURE_SPEECH_KEY')
speech_region = os.getenv('AZURE_SPEECH_REGION')

if not speech_key or not speech_region:
    logger.error("Azure Speech Service credentials are not set.")
    raise ValueError("Azure Speech Service credentials are not set.")

openai.api_key = os.getenv('AZURE_OPENAI_KEY')
openai.api_base = os.getenv('AZURE_OPENAI_ENDPOINT')
openai.api_type = 'azure'
openai.api_version = '2023-03-15-preview'  # Update if necessary
deployment_name = os.getenv('AZURE_OPENAI_DEPLOYMENT')

def speech_to_text_with_timestamps(audio_file_path):
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    audio_input = speechsdk.AudioConfig(filename=audio_file_path)
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_input)
    
    # List to hold caption data with timestamps
    captions = []
    
    done = False

    def recognized_handler(evt):
        nonlocal captions
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            logger.info(f"Recognized speech: {evt.result.text}")
            # Append the recognized text and its offset
            captions.append({
                "text": evt.result.text,
                "offset": evt.result.offset,  # in ticks (100-nanosecond units)
                "duration": evt.result.duration  # in ticks
            })
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            logger.info("No speech could be recognized")

    def session_event_handler(evt):
        nonlocal done
        logger.info(f'Session event: {evt}')
        done = True

    speech_recognizer.recognized.connect(recognized_handler)
    speech_recognizer.session_started.connect(lambda evt: logger.info(f'Session started: {evt}'))
    speech_recognizer.session_stopped.connect(session_event_handler)
    speech_recognizer.canceled.connect(session_event_handler)

    speech_recognizer.start_continuous_recognition()
    logger.info("Started continuous speech recognition.")

    while not done:
        import time
        time.sleep(0.5)

    speech_recognizer.stop_continuous_recognition()
    logger.info("Stopped continuous speech recognition.")

    # Convert ticks to seconds and format timestamps
    for caption in captions:
        start_seconds = caption["offset"] / 10_000_000  # Convert ticks to seconds
        end_seconds = (caption["offset"] + caption["duration"]) / 10_000_000
        caption["start_time"] = format_time(start_seconds)
        caption["end_time"] = format_time(end_seconds)
        del caption["offset"]
        del caption["duration"]

    logger.info(f"Captions with timestamps: {captions}")
    return captions

def format_time(seconds):
    """Helper function to format seconds into HH:MM:SS.mmm"""
    millis = int((seconds - int(seconds)) * 1000)
    sec = int(seconds) % 60
    minutes = (int(seconds) // 60) % 60
    hours = int(seconds) // 3600
    return f"{hours:02}:{minutes:02}:{sec:02}.{millis:03}"

def generate_srt(captions):
    srt = ""
    for idx, caption in enumerate(captions, start=1):
        srt += f"{idx}\n"
        srt += f"{caption['start_time']} --> {caption['end_time']}\n"
        srt += f"{caption['text']}\n\n"
    return srt

def embed_captions_into_video(video_path, srt_path, output_video_path):
    (
        ffmpeg
        .input(video_path)
        .output(output_video_path, vf=f"subtitles={srt_path}")
        .overwrite_output()
        .run(quiet=False)
    )
    logger.info(f"Embedded captions into video: {output_video_path}")

@app.post("/upload_and_caption")
async def upload_and_caption(file: UploadFile = File(...)):
    logger.info("upload_and_caption endpoint called")

    # Check file type
    if file.content_type not in ['audio/mpeg', 'audio/wav', 'video/mp4']:
        logger.error(f"Unsupported file type: {file.content_type}")
        return JSONResponse(content={"error": "Unsupported file type."}, status_code=400)

    # Save the uploaded file temporarily
    temp_dir = Path("./temp")
    temp_dir.mkdir(exist_ok=True)
    input_file_path = temp_dir / file.filename

    try:
        with open(input_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved uploaded file to {input_file_path}")
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        return JSONResponse(content={"error": "Failed to save uploaded file."}, status_code=500)

    # Convert or extract audio as needed
    converted_file_path = temp_dir / f"{input_file_path.stem}_converted.wav"

    try:
        if file.content_type == 'audio/wav':
            # No conversion needed
            converted_file_path = input_file_path
            logger.info("No conversion needed for WAV file.")
        elif file.content_type.startswith('video/'):
            # Extract audio from video
            logger.info("Extracting audio from video file.")
            (
                ffmpeg
                .input(str(input_file_path))
                .output(str(converted_file_path), format='wav', acodec='pcm_s16le', ac=1, ar='16000')
                .overwrite_output()
                .run(quiet=False)
            )
            logger.info("Audio extraction completed.")
        else:
            # Use ffmpeg to convert to WAV format
            logger.info("Converting audio file to WAV format.")
            (
                ffmpeg
                .input(str(input_file_path))
                .output(str(converted_file_path), format='wav', acodec='pcm_s16le', ac=1, ar='16000')
                .overwrite_output()
                .run(quiet=False)
            )
            logger.info("Audio conversion completed.")
    except ffmpeg.Error as e:
        error_message = f"FFmpeg error: {e.stderr.decode()}"
        logger.error(error_message)
        return JSONResponse(content={"error": error_message}, status_code=500)
    except Exception as e:
        error_message = f"Error converting file: {str(e)}"
        logger.error(error_message)
        return JSONResponse(content={"error": error_message}, status_code=500)

    # Perform speech-to-text captioning with timestamps
    try:
        captions = speech_to_text_with_timestamps(str(converted_file_path))
    except Exception as e:
        error_message = f"Error during speech recognition: {str(e)}"
        logger.error(error_message)
        return JSONResponse(content={"error": error_message}, status_code=500)
    finally:
        # Clean up temporary files
        try:
            input_file_path.unlink()
            if converted_file_path != input_file_path:
                converted_file_path.unlink()
            logger.info("Temporary files cleaned up.")
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up files: {cleanup_error}")

    # Generate SRT file
    srt_content = generate_srt(captions)
    srt_file_path = temp_dir / f"{input_file_path.stem}.srt"
    try:
        with open(srt_file_path, "w", encoding="utf-8") as srt_file:
            srt_file.write(srt_content)
        logger.info(f"SRT file saved to {srt_file_path}")
    except Exception as e:
        logger.error(f"Error saving SRT file: {e}")
        return JSONResponse(content={"error": "Failed to generate SRT file."}, status_code=500)

    # Optionally, embed captions into video
    # Uncomment the following lines if you want to embed captions
    # output_video_path = temp_dir / f"{input_file_path.stem}_with_captions.mp4"
    # try:
    #     embed_captions_into_video(str(input_file_path), str(srt_file_path), str(output_video_path))
    # except Exception as e:
    #     logger.error(f"Error embedding captions into video: {e}")
    #     return JSONResponse(content={"error": "Failed to embed captions into video."}, status_code=500)

    # Return captions and SRT content as JSON
    return {
        "captions": captions,
        "srt": srt_content
    }
