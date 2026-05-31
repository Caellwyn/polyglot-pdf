

# genai.live module

## full genai docs available at https://googleapis.github.io/python-genai/
[Preview] Live API client.

class genai.live.AsyncLive(api_client)
Bases: BaseModule

[Preview] AsyncLive.

connect(*, model, config=None)
[Preview] Connect to the live server.

Note: the live API is currently in preview.

Usage:

client = genai.Client(api_key=API_KEY)
config = {}
async with client.aio.live.connect(model='...', config=config) as session:
  await session.send_client_content(
    turns=types.Content(
      role='user',
      parts=[types.Part(text='hello!')]
    ),
    turn_complete=True
  )
  async for message in session.receive():
    print(message)
Return type:
AsyncIterator[AsyncSession]

Parameters:
model – The model to use for the live session.

config – The configuration for the live session.

**kwargs – additional keyword arguments.

Yields:
An AsyncSession object.

property music: AsyncLiveMusic
class genai.live.AsyncSession(api_client, websocket, session_id=None, setup_complete=None)
Bases: object

[Preview] AsyncSession.

async close()
Return type:
None

async receive()
Receive model responses from the server.

The method will yield the model responses from the server. The returned responses will represent a complete model turn. When the returned message is function call, user must call send with the function response to continue the turn.

Return type:
AsyncIterator[LiveServerMessage]

Yields:
The model responses from the server.

Example usage:

client = genai.Client(api_key=API_KEY)

async with client.aio.live.connect(model='...') as session:
  await session.send(input='Hello world!', end_of_turn=True)
  async for message in session.receive():
    print(message)
async send(*, input=None, end_of_turn=False)
[Deprecated] Send input to the model.

> Warning: This method is deprecated and will be removed in a future version (not before Q3 2025). Please use one of the more specific methods: send_client_content, send_realtime_input, or send_tool_response instead.

The method will send the input request to the server.

Return type:
None

Parameters:
input – The input request to the model.

end_of_turn – Whether the input is the last message in a turn.

Example usage:

client = genai.Client(api_key=API_KEY)

async with client.aio.live.connect(model='...') as session:
  await session.send(input='Hello world!', end_of_turn=True)
  async for message in session.receive():
    print(message)
async send_client_content(*, turns=None, turn_complete=True)
Send non-realtime, turn based content to the model.

There are two ways to send messages to the live API: send_client_content and send_realtime_input.

send_client_content messages are added to the model context in order. Having a conversation using send_client_content messages is roughly equivalent to using the Chat.send_message_stream method, except that the state of the chat history is stored on the API server.

Because of send_client_content’s order guarantee, the model cannot respond as quickly to send_client_content messages as to send_realtime_input messages. This makes the biggest difference when sending objects that have significant preprocessing time (typically images).

The send_client_content message sends a list of Content objects, which has more options than the media:Blob sent by send_realtime_input.

The main use-cases for send_client_content over send_realtime_input are:

Prefilling a conversation context (including sending anything that can’t be represented as a realtime message), before starting a realtime conversation.

Conducting a non-realtime conversation, similar to client.chat, using the live api.

Caution: Interleaving send_client_content and send_realtime_input
in the same conversation is not recommended and can lead to unexpected results.

Parameters:
turns – A Content object or list of Content objects (or equivalent dicts).

turn_complete – if true (the default) the model will reply immediately. If false, the model will wait for you to send additional client_content, and will not return until you send turn_complete=True.

Example:

import google.genai
from google.genai import types
import os

if os.environ.get('GOOGLE_GENAI_USE_ENTERPRISE'):
  MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'
else:
  MODEL_NAME = 'gemini-live-2.5-flash-preview';

client = genai.Client()
async with client.aio.live.connect(
    model=MODEL_NAME,
    config={"response_modalities": ["TEXT"]}
) as session:
  await session.send_client_content(
      turns=types.Content(
          role='user',
          parts=[types.Part(text="Hello world!")]))
  async for msg in session.receive():
    if msg.text:
      print(msg.text)
Return type:
None

async send_realtime_input(*, media=None, audio=None, audio_stream_end=None, video=None, text=None, activity_start=None, activity_end=None)
Send realtime input to the model, only send one argument per call.

Use send_realtime_input for realtime audio chunks and video frames(images).

With send_realtime_input the api will respond to audio automatically based on voice activity detection (VAD).

send_realtime_input is optimized for responsivness at the expense of deterministic ordering. Audio and video tokens are added to the context when they become available.

Return type:
None

Parameters:
media – A Blob-like object, the realtime media to send.

Example:

from pathlib import Path

from google import genai
from google.genai import types

import PIL.Image

import os

if os.environ.get('GOOGLE_GENAI_USE_ENTERPRISE'):
  MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'
else:
  MODEL_NAME = 'gemini-live-2.5-flash-preview';


client = genai.Client()

async with client.aio.live.connect(
    model=MODEL_NAME,
    config={"response_modalities": ["TEXT"]},
) as session:
  await session.send_realtime_input(
      media=PIL.Image.open('image.jpg'))

  audio_bytes = Path('audio.pcm').read_bytes()
  await session.send_realtime_input(
      media=types.Blob(data=audio_bytes, mime_type='audio/pcm;rate=16000'))

  async for msg in session.receive():
    if msg.text is not None:
      print(f'{msg.text}')
async send_tool_response(*, function_responses)
Send a tool response to the session.

Use send_tool_response to reply to LiveServerToolCall messages from the server.

To set the available tools, use the config.tools argument when you connect to the session (client.live.connect).

Return type:
None

Parameters:
function_responses – A FunctionResponse-like object or list of FunctionResponse-like objects.

Example:

from google import genai
from google.genai import types

import os

if os.environ.get('GOOGLE_GENAI_USE_ENTERPRISE'):
  MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'
else:
  MODEL_NAME = 'gemini-live-2.5-flash-preview';

client = genai.Client()

tools = [{'function_declarations': [{'name': 'turn_on_the_lights'}]}]
config = {
    "tools": tools,
    "response_modalities": ['TEXT']
}

async with client.aio.live.connect(
    model='models/gemini-live-2.5-flash-preview',
    config=config
) as session:
  prompt = "Turn on the lights please"
  await session.send_client_content(
      turns={"parts": [{'text': prompt}]}
  )

  async for chunk in session.receive():
      if chunk.server_content:
        if chunk.text is not None:
          print(chunk.text)
      elif chunk.tool_call:
        print(chunk.tool_call)
        print('_'*80)
        function_response=types.FunctionResponse(
                name='turn_on_the_lights',
                response={'result': 'ok'},
                id=chunk.tool_call.function_calls[0].id,
            )
        print(function_response)
        await session.send_tool_response(
            function_responses=function_response
        )

        print('_'*80)
async start_stream(*, stream, mime_type)
[Deprecated] Start a live session from a data stream.

> Warning: This method is deprecated and will be removed in a future version (not before Q2 2025). Please use one of the more specific methods: send_client_content, send_realtime_input, or send_tool_response instead.

The interaction terminates when the input stream is complete. This method will start two async tasks. One task will be used to send the input stream to the model and the other task will be used to receive the responses from the model.

Return type:
AsyncIterator[LiveServerMessage]

Parameters:
stream – An iterator that yields the model response.

mime_type – The MIME type of the data in the stream.

Yields:
The audio bytes received from the model and server response messages.

Example usage:

client = genai.Client(api_key=API_KEY)
config = {'response_modalities': ['AUDIO']}
async def audio_stream():
  stream = read_audio()
  for data in stream:
    yield data
async with client.aio.live.connect(model='...', config=config) as session:
  for audio in session.start_stream(stream = audio_stream(),
  mime_type = 'audio/pcm'):
    play_audio_chunk(audio.data)