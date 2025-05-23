import openai
import json

# Global variables
client = None
messages = []

# System prompt to guide the assistant
instruction = """You are a scenario adapter who takes on the given role and assists with practice conversations and 
vocabulary building. Your responses should be limited to three lines.
"""
messages.append({"role": "system", "content": instruction})


def init_openai_client(auth_key_val, system_audio_val, user_audio_val, feedback_json_val, quiz_json_val, conversation_txt_val):
    """
    Initializes the OpenAI client and sets global paths for files.

    Parameters:
        auth_key_val (str): Path to the API key file.
        system_audio_val (str): Path to save generated system audio.
        user_audio_val (str): Path to the user audio input.
        feedback_json_val (str): Path to store feedback JSON.
        quiz_json_val (str): Path to store generated quiz.
        conversation_txt_val (str): Path to save ongoing conversation log.
    """
    global auth_key, system_audio, user_audio, feedback_json, quiz_json, conversation_txt
    auth_key, system_audio, user_audio = auth_key_val, system_audio_val, user_audio_val
    feedback_json, quiz_json, conversation_txt = feedback_json_val, quiz_json_val, conversation_txt_val

    with open(auth_key, "r") as key_file:
        key = key_file.read().strip()

    global client
    client = openai.OpenAI(api_key=key)


def create_quiz():
    """
    Generates a short grammar and phrasing quiz from feedback JSON content and saves it to a file.
    """
    with open(feedback_json, "r") as file:
        data = json.load(file)

    prompt = f"""
    You are a helpful English tutor. 
    Using the following list of grammar mistakes and corrected phrases, create short one-line quiz questions. 
    Each question should ask the user to choose or correct a phrase to avoid a past mistake. Then provide the correct answer.
    Provide questions such a way to see if I am making use of better pharses.

    Examples:
    Q: Which is correct? "I taked" or "I took"?  
    A: I took.

    Q: Fix this sentence: "I not even start."  
    A: I haven't even started.


    Grammar Mistakes:
    {"\n".join(data["grammar_mistakes"])}

    Corrected Phrases:
    {"\n".join(data["better_phrases"])}

    Better vocabulary:
    {"\n".join(data["better_vocabulary"])}

    Generate similar quiz questions and answers for each item
    """

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an English tutor helping the user correct grammar mistakes."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    quiz_content = response.choices[0].message.content

    # Extract question and answers
    quiz_qa_pairs = []
    question, answer = "", ""
    for line in quiz_content.splitlines():
        if line.strip().startswith("Q:"):
            question = line.strip()[2:].strip()
        elif line.strip().startswith("A:"):
            answer = line.strip()[2:].strip()
            if question and answer:
                quiz_qa_pairs.append({
                    "question": question,
                    "answer": answer
                })
            question, answer = "", ""

    # Save to JSON
    with open(quiz_json, "w") as outfile:
        json.dump(quiz_qa_pairs, outfile, indent=4)

def conversation_corrector(fix_json=False, invalid_json=None):
    """
    Analyzes the user's conversation for grammar issues and provides suggestions.

    Parameters:
        fix_json (bool): Whether to fix a broken JSON response.
        invalid_json (str): The invalid JSON text to attempt to correct.
    """
    if fix_json:
        prompt = f"""
        JSON: {invalid_json} I got json.JSONDecodeError, please fix the JSON content for loading and dumping.
        Ensure the output is a **valid JSON object** with no markdown, extra text, or formatting.
        """
    else:
        with open(conversation_txt, "r") as txt_file:
            conv = txt_file.read()

        prompt = f"""
        Analyze the following conversation and provide feedback for improvement in the **You** section only (i.e., the person learning English). Output a single valid **JSON object** with the following exact keys:

        1. "grammar_mistakes":  A dictionary where each key is a sentence spoken by "You" that contains a grammar issue, and the value is the corrected version. Focus on tense, articles, prepositions, and subject-verb agreement.

        2. "better_vocabulary":  A dictionary where each key is a simple, awkward, or repetitive word/phrase used by "You", and the value is a more fluent, natural, or advanced alternative.

        3. "better_phrases":  A dictionary where each key is an unnatural or informal sentence/phrase used by "You", and the value is a more appropriate, fluent, or professional version. This includes:
        - Awkward sentence structures (even if grammatically correct)
        - Redundant expressions
        - Improvements for formality (especially suitable for academic, interview, or visa contexts)

        Instructions:
        - DO NOT duplicate corrections across sections.
        - If no suggestions for a section, return an empty object: {{}}
        - Limit each correction list (1-3) to a maximum of 7 relevant items.
        - Ensure the output is a **valid JSON object** with no markdown, extra text, or formatting.

        Conversation:
        {conv}
        """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )

    result_text = response.choices[0].message.content

    try:
        result_json = json.loads(result_text)
        json_object = json.dumps(result_json, indent=2)
        with open(feedback_json, "w") as outfile:
            outfile.write(json_object)
    except json.JSONDecodeError:
        print("The model didn't return valid JSON.")
        conversation_corrector(fix_json=True, invalid_json=result_text)


def conversation_builder(user_input):
    """
    Adds user input to the conversation, gets the assistant's response, appends both to log and returns the reply.

    Parameters:
        user_input (str): The user's message.

    Returns:
        str: Assistant's reply.
    """
    global messages
    messages.append({"role": "user", "content": "You: " + user_input})

    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )

    reply = response.choices[0].message.content.strip()
    messages.append({"role": "assistant", "content": reply})

    with open(conversation_txt, "a") as f:
        f.write(f"You: {user_input}\nSystem: {reply}\n")

    return reply


def speech_to_text():
    """
    Transcribes user audio input using OpenAI's audio transcription.

    Returns:
        str: Transcribed text.
    """
    with open(user_audio, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=audio_file
        )
    return transcription.text


def text_to_speech(input_text):
    """
    Converts input text to speech and saves the audio output.

    Parameters:
        input_text (str): The text to convert to speech.
    """
    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=input_text
    )

    with open(system_audio, "wb") as f:
        f.write(response.content)


def delete_chat_history():
    """
    Resets conversation to the system instruction and clears the log file.
    """
    global messages
    messages = messages[:1]  # Keep only the system instruction
    open(conversation_txt, "w").close()
