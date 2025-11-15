import os
import json
from google import genai
from google.genai import types
from google.api_core import exceptions
from google.cloud import secretmanager
from pydantic import BaseModel, Field
from datetime import timedelta
from typing import List, Dict, Any, Optional

# --- 0. CONFIGURATION & ENVIRONMENT SETUP ---

# NOTE: Replace 'YOUR_PROJECT_ID' with your actual Google Cloud Project ID.
# In a real environment, project ID would be read from ENV variables.

class Settings:
    """Application-wide configuration settings."""
    # Set the Time-to-Live (TTL) for the cached content (in days).
    CACHE_TTL_DAYS = 30
    
    # Path to the local master annotated PDF file (e.g., the blank form).
    I90_PDF_PATH = os.environ.get("I90_PDF_PATH", "mock_annotated_i90_master.pdf") 
    
    # Secret Manager resource path to store the active cache reference ID.
    # Replace 'YOUR_PROJECT_ID' placeholder with os.environ.get('GCP_PROJECT_ID')
    SECRET_CACHE_ID_NAME = "projects/YOUR_PROJECT_ID/secrets/GEMINI_I90_CACHE_ID"
    
    # The Gemini model used for caching. Caches are model-specific.
    MODEL_NAME = "gemini-2.5-flash" 

SETTINGS = Settings()

# --- 1. CONVERSATIONAL OUTPUT CONTRACT (For Backend TTS/History) ---

class ConversationalResponse(BaseModel):
    """The structured output required by the backend for TTS and saving history."""
    user_language: str = Field(description="The ISO 639-1 code (e.g., 'en', 'es') of the user's spoken language.")
    transcript_of_input_audio: str = Field(description="The full text transcript of the user's last audio input.")
    model_response: str = Field(description="The conversational text response from the model to be sent to the TTS engine.")
    
    # This list allows the model to instruct the front-end to take actions.
    # Note: The 'function_name' should match your defined front-end tools
    # (e.g., 'update_form_field', 'query_form_value').
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        None, 
        description="A list of tool calls (function_name and args) to query or update form fields on the front end, if required by the conversation flow."
    )

GUIDANCE_OUTPUT_SCHEMA_JSON = ConversationalResponse.model_json_schema()


# --- 2. KNOWLEDGE BASE LOADING ---

# Load the full structural schema JSON content once at module import time.
# This prevents repeated file reading during cache renewal attempts.
try:
    # Use the simulated content for the purposes of this code example
    FULL_FORM_SCHEMA_CONTENT = """
    {
      "source": "pdf",
      "form_metadata": {
        "title": "Form I-90, Application to Replace Permanent Residence Card",
        "form_number": "I-90",
        "edition_date": "01/20/25",
        "version": "v9_conformant"
      },
      "sections": [
        {
          "id": "Part 1 - Information About You",
          "fields": [
            {"id": "p1_line1_aliennumber", "label": "Alien Registration Number. (A. Number). "},
            {"id": "p1_line3a_familyname", "label": "Family Name (Last Name)"},
            // ... hundreds of fields follow ...
          ]
        }
      ],
      "knowledge_hints": {
          "p1_line1_aliennumber": "The A-Number can be found on EAD, I-797 notices, or immigrant visa stamp if the Green Card is lost."
      }
    }
    """
    # Note: In a production environment, you would use: 
    # with open("schema.json", "r") as f:
    #     FULL_FORM_SCHEMA_CONTENT = f.read()

except FileNotFoundError:
    print("Warning: schema.json not found. Full Form Schema content initialized to empty string.")
    FULL_FORM_SCHEMA_CONTENT = ""


# --- 3. CLOUD RESOURCE HELPERS ---

# Note: genai.Client() is initialized lazily in the core functions to ensure
# it uses the most current environment configuration.

def _get_cache_id_from_secret_manager() -> str | None:
    """Retrieves the current active cache reference ID from Secret Manager."""
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        # Request the latest version of the secret
        name = f"{SETTINGS.SECRET_CACHE_ID_NAME}/versions/latest"
        response = sm_client.access_secret_version(request={"name": name})
        cache_id = response.payload.data.decode('utf-8').strip()
        print(f"Secret Manager: Retrieved active cache ID: {cache_id}")
        return cache_id
    except exceptions.NotFound:
        # Expected exception if secret has never been created or version destroyed
        print("Secret Manager: Cache ID secret not found or empty.")
        return None
    except Exception as e:
        # Catch other exceptions like authentication or network errors
        print(f"Error accessing Secret Manager: {e}")
        return None

def _store_cache_id_in_secret_manager(cache_id: str):
    """Updates the Secret Manager with the new active cache reference ID."""
    try:
        sm_client = secretmanager.SecretManagerServiceClient()
        # Add a new version with the cache ID as the payload
        sm_client.add_secret_version(
            request={
                "parent": SETTINGS.SECRET_CACHE_ID_NAME,
                "payload": {"data": cache_id.encode('utf-8')}
            }
        )
        print(f"Secret Manager: Successfully updated with new cache ID: {cache_id}")
    except Exception as e:
        print(f"Error storing cache ID in Secret Manager: {e}")

def _delete_old_cache(client: genai.Client, old_cache_id: str):
    """Deletes a content cache resource if it exists."""
    if not old_cache_id or not old_cache_id.startswith("caches/"):
        return
    
    try:
        # Only attempt deletion if the ID is valid
        client.caches.delete(name=old_cache_id)
        print(f"Cleanup: Successfully deleted old cache: {old_cache_id}")
    except exceptions.NotFound:
        pass 
    except Exception as e:
        print(f"Error deleting old cache {old_cache_id}: {e}")


# --- 4. CACHE MANAGEMENT LOGIC (CORE) ---

def _create_new_cache_content(client: genai.Client, old_cache_id: str | None) -> types.CachedContent | None:
    """
    Handles the entire creation process: PDF upload, cache creation,
    and temporary file cleanup.
    """
    
    # 1. Input Validation
    if not os.path.exists(SETTINGS.I90_PDF_PATH):
        print(f"CRITICAL ERROR: PDF file not found at path: {SETTINGS.I90_PDF_PATH}")
        return None
        
    # 2. Upload the PDF File
    print(f"Caching: Uploading PDF from: {SETTINGS.I90_PDF_PATH}...")
    try:
        uploaded_file = client.files.upload(
            file=SETTINGS.I90_PDF_PATH,
            config=dict(mime_type='application/pdf')
        )
    except Exception as e:
        print(f"Error uploading PDF file: {e}")
        return None
    
    # 3. Define the Content to be Cached
    SYSTEM_INSTRUCTION = (
        f"You are an expert USCIS {os.path.basename(SETTINGS.I90_PDF_PATH)} Form Assistant. "
        "Your task is purely conversational: provide accurate, supportive guidance, answer "
        "document-specific questions, and determine the next logical form field to prompt the user for. "
        "You MUST use the entire structural schema provided below to guide your conversational flow and "
        "to reference correct field IDs for tool calls."
    )
    
    # Contents includes the PDF, the System Instruction, and the Full Structural Schema Text
    full_knowledge_content = [
        uploaded_file,
        types.Part.from_text(SYSTEM_INSTRUCTION),
        types.Part.from_text(f"\n--- FULL FORM SCHEMA KNOWLEDGE BASE ---\n{FULL_FORM_SCHEMA_CONTENT}")
    ]

    # Define the tool configuration for the REQUIRED OUTPUT CONTRACT
    tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="return_conversational_response", 
                    description="Formats the model's final conversational response and any required tool actions for the backend. Must be used for all final outputs.",
                    parameters=types.Schema.from_dict(GUIDANCE_OUTPUT_SCHEMA_JSON)
                )
            ]
        )
    ]
    
    # Convert TTL to the required seconds string format (e.g., "2592000s")
    ttl_seconds = str(timedelta(days=SETTINGS.CACHE_TTL_DAYS).total_seconds()).split('.')[0] + "s"

    # 4. Create the Cache
    print(f"Caching: Creating new explicit cache with TTL: {SETTINGS.CACHE_TTL_DAYS} days...")
    try:
        i90_cache = client.caches.create(
            model=SETTINGS.MODEL_NAME,
            contents=full_knowledge_content,
            config=types.CreateCachedContentConfig(
                tools=tools, # Caching the REQUIRED OUTPUT FORMAT
                ttl=ttl_seconds
            )
        )
        print(f"✅ Cache created successfully. Name: {i90_cache.name}")
        
        # 5. Cleanup and Update Secret Manager
        _store_cache_id_in_secret_manager(i90_cache.name)
        client.files.delete(name=uploaded_file.name)
        print(f"Cleanup: Deleted temporary file: {uploaded_file.name}")
        
        if old_cache_id:
            # Delete old cache AFTER new cache is successfully created and secret is updated
            _delete_old_cache(client, old_cache_id) 
            
        return i90_cache

    except Exception as e:
        print(f"CRITICAL ERROR: Could not create cache content: {e}")
        # Note: Must also clean up the uploaded file if cache creation fails here!
        try:
             client.files.delete(name=uploaded_file.name)
             print("Cleanup: Deleted uncommitted uploaded file due to failure.")
        except:
             pass
        return None


def get_or_refresh_active_cache_id() -> str | None:
    """
    Orchestrator function. Checks for a valid cache, or creates and updates it.
    """
    client = genai.Client()
    current_cache_id = _get_cache_id_from_secret_manager()
    old_cache_id = None
    
    if current_cache_id and current_cache_id.startswith("caches/"):
        print(f"Validation: Checking status of existing cache: {current_cache_id}")
        try:
            cache_object = client.caches.get(name=current_cache_id)
            if cache_object.state == types.CachedContent.State.READY:
                # Cache is valid and ready, use it immediately
                return current_cache_id
            else:
                print(f"Validation: Cache state is {cache_object.state}. Needs renewal.")
                old_cache_id = current_cache_id
        except exceptions.NotFound:
            print("Validation: Existing cache is expired or destroyed (NotFound). Needs renewal.")
            old_cache_id = current_cache_id
        except Exception as e:
            print(f"Validation Error: Could not check cache status: {e}. Needs renewal.")
            old_cache_id = current_cache_id

    # If renewal is necessary or no ID existed, create a new cache
    print("Initiating cache creation/renewal process...")
    
    # Pass the old_cache_id so that _create_new_cache_content can delete it 
    # *after* the new one is successfully created.
    new_cache = _create_new_cache_content(client, old_cache_id)
    
    if new_cache:
        return new_cache.name
    
    return None


# --- 5. BACKEND USAGE FUNCTION ---

def process_user_request(conversation_history: List[Dict[str, str]], user_audio_transcript: str, user_lang: str):
    """
    The main conversational function called by your backend.
    It leverages the cached knowledge for intelligent, structured responses.
    """
    
    # Ensure the cache is ready or created before every call
    active_cache_id = get_or_refresh_active_cache_id()
    
    if not active_cache_id:
        return "Error: Failed to secure an active cache reference. Cannot process request."

    print(f"\nProcessing request using active cache: {active_cache_id}")
    
    # 1. Construct the tool configuration required for the output
    tools_config = [types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="return_conversational_response",
                parameters=types.Schema.from_dict(GUIDANCE_OUTPUT_SCHEMA_JSON)
            )
        ]
    )]

    # 2. Construct the conversational prompt and history
    prompt_message = (
        f"The user's latest input transcript is: '{user_audio_transcript}'. "
        f"The user's current spoken language is: '{user_lang}'. "
        "Based on the conversation history (provided implicitly by 'contents'), the cached form schema, and the annotated PDF, formulate a concise, helpful response. "
        "If you need to know a form field value, use the tool call to query it. If the user provides a value, use the tool call to update the field. Use the cached knowledge to answer 'where to find' questions."
    )
    
    history_parts = []
    for turn in conversation_history:
        history_parts.append(types.Content(
            role=turn.get('role', 'user'), # Default to user role if not specified
            parts=[types.Part.from_text(turn.get('text', ''))]
        ))
    
    # Add the current user prompt
    history_parts.append(types.Content(
        role="user", 
        parts=[types.Part.from_text(prompt_message)]
    ))


    # 3. Call the Model
    try:
        client = genai.Client()
        response = client.models.generate_content(
            model=SETTINGS.MODEL_NAME,
            contents=history_parts,
            config=types.GenerateContentConfig(
                cached_content=active_cache_id,
                tools=tools_config
            )
        )

        # 4. Process the structured output (required by your design)
        if response.function_calls:
            func_call = response.function_calls[0]
            if func_call.name == "return_conversational_response":
                return json.dumps(func_call.args, indent=2)
            else:
                return f"Error: Model called unexpected function: {func_call.name}"
        else:
            return f"Error: Model did not return a structured response. Text: {response.text}"

    except Exception as e:
        print(f"Error during content generation: {e}")
        return "Error: Content generation failed during API call."


# --- EXAMPLE USAGE SIMULATION ---
if __name__ == '__main__':
    
    # WARNING: This test block WILL FAIL unless you replace the placeholder path 
    # 'mock_annotated_i90_master.pdf' with a valid local PDF file (even a dummy one) 
    # AND configure your GCP environment for Secret Manager access.

    if not os.path.exists(SETTINGS.I90_PDF_PATH):
        print("\n--- TEST SETUP WARNING ---")
        print(f"Creating a mock PDF file at '{SETTINGS.I90_PDF_PATH}' for test purposes.")
        try:
            with open(SETTINGS.I90_PDF_PATH, 'w') as f:
                f.write("This is a mock PDF file content for caching demonstration.")
        except Exception as e:
             print(f"Could not create mock file. Please create it manually: {e}")
    
    MOCK_CONVERSATION_HISTORY = [
        {
            "role": "user",
            "text": "Hello, I want to start my Green Card replacement application."
        },
        {
            "role": "model",
            "text": "Welcome! I can guide you through the I-90 form. Let's begin with Part 1, Item 1.1: What is your Alien Registration Number (A-Number)?"
        }
    ]
    
    MOCK_USER_TRANSCRIPT = "I lost my green card, where else can I find it?"
    MOCK_USER_LANGUAGE = "en"
    
    print("\n--- STARTING CONVERSATIONAL TEST ---")
    
    # The function will first check Secret Manager, create the cache if needed, 
    # update the secret, and then run the generative call using the cache.
    final_structured_response = process_user_request(
        MOCK_CONVERSATION_HISTORY, 
        MOCK_USER_TRANSCRIPT, 
        MOCK_USER_LANGUAGE
    )
    
    print("\n--- FINAL STRUCTURED RESPONSE (For TTS/Backend) ---")
    print(final_structured_response)