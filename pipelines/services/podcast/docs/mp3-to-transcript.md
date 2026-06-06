# MP3 to Transcript Conversion Methods

This document outlines different services and methods for converting MP3 audio files to text transcripts.

## Cost Comparison

| Service | Cost for 1,000 hours |
|---------|---------------------|
| Local Whisper | $0 (free) |
| Deepgram | ~$180–$270 |
| AssemblyAI | ~$270 |
| OpenAI Whisper API | ~$600 |
| Google Cloud | ~$960–$1,440 |
| Azure | ~$1,000–$1,200 |

## 1. Local Whisper (Free)

**Best for:** Privacy-sensitive content, unlimited usage, offline processing

### Overview
OpenAI's Whisper model running locally on your machine. Completely free but requires computational resources.

### Pros
- ✅ Completely free (no API costs)
- ✅ Privacy: audio never leaves your machine
- ✅ No rate limits
- ✅ Supports 99 languages
- ✅ Can run offline

### Cons
- ❌ Requires GPU for fast processing (CPU is slow)
- ❌ High memory usage
- ❌ Setup complexity
- ❌ Slower than cloud APIs

### Setup

**Install Whisper:**
```bash
pip install openai-whisper
# Or with uv:
uv pip install openai-whisper
```

**Basic Usage:**
```python
import whisper

model = whisper.load_model("base")  # Options: tiny, base, small, medium, large
result = model.transcribe("audio.mp3")
print(result["text"])
```

**Model Sizes:**
- `tiny`: Fastest, least accurate
- `base`: Good balance
- `small`: Better accuracy
- `medium`: High accuracy
- `large`: Best accuracy, slowest

### Requirements
- Python 3.8+
- FFmpeg (for audio processing)
- GPU recommended (CUDA) for faster processing

---

## 2. Deepgram

**Best for:** Fast, accurate transcription with good pricing

### Overview
Cloud-based speech-to-text API with competitive pricing and fast processing.

### Pros
- ✅ Fast processing
- ✅ Competitive pricing
- ✅ Good accuracy
- ✅ Real-time transcription support
- ✅ Multiple language support

### Cons
- ❌ Requires API key
- ❌ Audio sent to cloud
- ❌ Rate limits apply

### Setup

**Install:**
```bash
pip install deepgram-sdk
```

**Basic Usage:**
```python
from deepgram import DeepgramClient, PrerecordedOptions

# Initialize client
deepgram = DeepgramClient("YOUR_API_KEY")

# Transcribe
with open("audio.mp3", "rb") as audio_file:
    options = PrerecordedOptions(
        model="nova-2",
        language="en",
        punctuate=True,
    )
    response = deepgram.listen.rest.v("1").transcribe_file(
        {"buffer": audio_file}, options
    )
    transcript = response.results.channels[0].alternatives[0].transcript
    print(transcript)
```

### Pricing
- Pay-as-you-go: ~$0.18–$0.27 per hour
- Volume discounts available

---

## 3. AssemblyAI

**Best for:** High accuracy with additional features (speaker diarization, sentiment analysis)

### Overview
Cloud API with advanced features like speaker identification and sentiment analysis.

### Pros
- ✅ High accuracy
- ✅ Speaker diarization (identify who's speaking)
- ✅ Sentiment analysis
- ✅ Chapter detection
- ✅ Good documentation

### Cons
- ❌ More expensive than Deepgram
- ❌ Requires API key
- ❌ Audio sent to cloud

### Setup

**Install:**
```bash
pip install assemblyai
```

**Basic Usage:**
```python
import assemblyai as aai

aai.settings.api_key = "YOUR_API_KEY"
transcriber = aai.Transcriber()

transcript = transcriber.transcribe("audio.mp3")
print(transcript.text)

# With speaker labels
config = aai.TranscriptionConfig(speaker_labels=True)
transcript = transcriber.transcribe("audio.mp3", config=config)
```

### Pricing
- ~$0.27 per hour
- Free tier available (limited hours)

---

## 4. OpenAI Whisper API

**Best for:** High accuracy, simple API, OpenAI ecosystem integration

### Overview
OpenAI's hosted Whisper API service. Same model as local Whisper but managed by OpenAI.

### Pros
- ✅ High accuracy (same as local Whisper)
- ✅ Simple API
- ✅ No setup required
- ✅ Consistent performance

### Cons
- ❌ Most expensive option
- ❌ Requires API key
- ❌ Audio sent to cloud
- ❌ Rate limits

### Setup

**Install:**
```bash
pip install openai
```

**Basic Usage:**
```python
from openai import OpenAI

client = OpenAI(api_key="YOUR_API_KEY")

with open("audio.mp3", "rb") as audio_file:
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        language="en"
    )
    print(transcript.text)
```

### Pricing
- ~$0.60 per hour
- Pay-as-you-go

---

## 5. Google Cloud Speech-to-Text

**Best for:** Enterprise use, integration with Google Cloud ecosystem

### Overview
Google's cloud-based speech recognition service with enterprise features.

### Pros
- ✅ High accuracy
- ✅ Enterprise-grade reliability
- ✅ Multiple language support
- ✅ Custom models available
- ✅ Integration with Google Cloud services

### Cons
- ❌ Expensive
- ❌ Complex setup (requires Google Cloud account)
- ❌ Audio sent to cloud
- ❌ Steeper learning curve

### Setup

**Install:**
```bash
pip install google-cloud-speech
```

**Basic Usage:**
```python
from google.cloud import speech_v1
from google.cloud.speech_v1 import enums

client = speech_v1.SpeechClient()

with open("audio.mp3", "rb") as audio_file:
    audio = speech_v1.types.RecognitionAudio(content=audio_file.read())
    config = speech_v1.types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.MP3,
        sample_rate_hertz=16000,
        language_code="en-US",
    )
    response = client.recognize(config=config, audio=audio)
    for result in response.results:
        print(result.alternatives[0].transcript)
```

### Pricing
- ~$0.96–$1.44 per hour (varies by model and features)
- Free tier: 60 minutes/month

---

## 6. Azure Speech Services

**Best for:** Microsoft ecosystem integration, enterprise deployments

### Overview
Microsoft's cloud-based speech recognition service with enterprise features.

### Pros
- ✅ High accuracy
- ✅ Enterprise features
- ✅ Good Microsoft ecosystem integration
- ✅ Custom models available
- ✅ Real-time transcription

### Cons
- ❌ Expensive
- ❌ Complex setup (requires Azure account)
- ❌ Audio sent to cloud
- ❌ Steeper learning curve

### Setup

**Install:**
```bash
pip install azure-cognitiveservices-speech
```

**Basic Usage:**
```python
import azure.cognitiveservices.speech as speechsdk

speech_config = speechsdk.SpeechConfig(
    subscription="YOUR_SUBSCRIPTION_KEY",
    region="YOUR_REGION"
)

audio_config = speechsdk.audio.AudioConfig(filename="audio.mp3")
speech_recognizer = speechsdk.SpeechRecognizer(
    speech_config=speech_config,
    audio_config=audio_config
)

result = speech_recognizer.recognize_once()
print(result.text)
```

### Pricing
- ~$1.00–$1.20 per hour
- Free tier: 5 hours/month

---

## Recommendations

### For Personal/Privacy-Sensitive Projects
- **Local Whisper**: Free and keeps audio private

### For Cost-Conscious Projects
- **Deepgram**: Best balance of cost and quality

### For High Accuracy Needs
- **AssemblyAI** or **OpenAI Whisper API**: Best accuracy with additional features

### For Enterprise/Production
- **Google Cloud** or **Azure**: Enterprise-grade reliability and support

### For Quick Prototyping
- **OpenAI Whisper API**: Simplest setup and good accuracy

---

## Batch Processing Example

For processing multiple podcast episodes:

```python
import os
from pathlib import Path
import whisper  # or your chosen service

def transcribe_podcasts(downloads_dir, output_dir):
    model = whisper.load_model("base")
    
    for podcast_dir in Path(downloads_dir).iterdir():
        if podcast_dir.is_dir():
            for mp3_file in podcast_dir.glob("*.mp3"):
                print(f"Transcribing {mp3_file.name}...")
                result = model.transcribe(str(mp3_file))
                
                # Save transcript
                transcript_path = Path(output_dir) / podcast_dir.name / f"{mp3_file.stem}.txt"
                transcript_path.parent.mkdir(parents=True, exist_ok=True)
                transcript_path.write_text(result["text"], encoding="utf-8")

# Usage
transcribe_podcasts("./downloads", "./transcripts")
```

---

## Notes

- All pricing is approximate and may vary by region and usage volume
- Consider processing time vs. cost trade-offs
- For large-scale processing, local Whisper may require significant hardware investment
- Check each service's documentation for the latest pricing and features

