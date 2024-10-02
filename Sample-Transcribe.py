import asyncio
import os

# This example uses the sounddevice library to get an audio stream from the
# microphone. It's not a dependency of the project but can be installed with
# `python -m pip install amazon-transcribe aiofile`
# `pip install sounddevice`.
import sounddevice
import websockets

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

TRANSCRIBE_REGION = os.getenv('TRANSCRIBE_REGION', 'ap-southeast-1')
"""
Here's an example of a custom event handler you can extend to
process the returned transcription results as needed. This
handler will simply print the text out to your interpreter.
"""


class MyEventHandler(TranscriptResultStreamHandler):
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        results = transcript_event.transcript.results
        for result in results:
            for alt in result.alternatives:
                print(alt.transcript)


async def mic_stream():
    # This function wraps the raw input stream from the microphone forwarding
    # the blocks to an asyncio.Queue.
    loop = asyncio.get_event_loop()
    input_queue = asyncio.Queue()

    def callback(indata, frame_count, time_info, status):
        loop.call_soon_threadsafe(input_queue.put_nowait, (bytes(indata), status))

    # Be sure to use the correct parameters for the audio stream that matches
    # the audio formats described for the source language you'll be using:
    # https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html
    stream = sounddevice.RawInputStream(
        channels=1,
        samplerate=16000,
        callback=callback,
        blocksize=1024 * 2,
        dtype="int16",
    )
    # Initiate the audio stream and asynchronously yield the audio chunks
    # as they become available.
    with stream:
        while True:
            indata, status = await input_queue.get()
            yield indata, status


async def websocket_stream(websocket):
    # This function handles receiving audio from the client WebSocket.
    while True:
        try:
            # Receive raw audio data from the WebSocket connection
            audio_chunk = await websocket.recv()
            print(f"receive audio: {len(audio_chunk)}")
            yield audio_chunk, None  # Return audio data, no status
        except websockets.ConnectionClosed:
            print("Connection closed")
            break


# async def write_chunks(stream):
#     # This connects the raw audio chunks generator coming from the microphone
#     # and passes them along to the transcription stream.
#     async for chunk, status in mic_stream():
#         print(f"Chunk: {len(chunk)}")
#         await stream.input_stream.send_audio_event(audio_chunk=chunk)
#     await stream.input_stream.end_stream()

async def write_chunks(stream, websocket):
    # This connects the raw audio chunks generator coming from the WebSocket
    # and passes them along to the transcription stream.
    async for chunk, status in websocket_stream(websocket):
        print("sending chunk...")
        await stream.input_stream.send_audio_event(audio_chunk=chunk)
    await stream.input_stream.end_stream()


async def websocket_handler(websocket, path):
    # Setup up our client with our chosen AWS region
    client = TranscribeStreamingClient(region=TRANSCRIBE_REGION)

    # Start transcription to generate our async stream
    stream = await client.start_stream_transcription(
        language_code="en-US",
        media_sample_rate_hz=16000,
        media_encoding="pcm"
    )

    # Instantiate our handler and start processing events
    handler = MyEventHandler(stream.output_stream)
    await asyncio.gather(write_chunks(stream, websocket), handler.handle_events())


async def basic_transcribe():
    # Setup up our client with our chosen AWS region
    client = TranscribeStreamingClient(region=TRANSCRIBE_REGION)

    # Start transcription to generate our async stream
    stream = await client.start_stream_transcription(
        language_code="en-US",
        media_sample_rate_hz=16000,
        media_encoding="pcm"
    )

    # Instantiate our handler and start processing events
    handler = MyEventHandler(stream.output_stream)
    await asyncio.gather(write_chunks(stream), handler.handle_events())


# loop = asyncio.get_event_loop()
# loop.run_until_complete(basic_transcribe())
# loop.close()
# WebSocket server setup


async def main():
    async with websockets.serve(websocket_handler, "0.0.0.0", 8000):
        await asyncio.Future()  # Run forever


# Run the WebSocket server
asyncio.run(main())
