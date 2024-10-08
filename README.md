# Speech-to-Speech Application with Captioning

A FastAPI application that allows users to upload audio or video files, generates captions with timestamps using Azure Cognitive Services Speech SDK, and displays them on the frontend. The application is containerized using Docker for easy deployment.

## Features

- **Audio/Video Upload:** Users can upload `.mp3`, `.wav`, or `.mp4` files.
- **Speech-to-Text with Timestamps:** Generates captions with precise start and end times.
- **SRT File Generation:** Allows users to download captions in SRT format.
- **Frontend Interface:** User-friendly interface to upload files, view captions, and watch videos.
- **Dockerized:** Easy to deploy using Docker.

## Prerequisites

- **Docker:** Ensure Docker is installed on your system. [Install Docker](https://docs.docker.com/get-docker/)
- **Azure Cognitive Services Speech SDK:** Obtain your Azure Speech Service credentials.
- **OpenAI API Key:** If using OpenAI features.

## Setup Instructions

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/yourusername/speech_app.git
   cd speech_app
