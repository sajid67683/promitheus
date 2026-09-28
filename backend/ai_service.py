import os
from google import genai
import json
import re
from dotenv import load_dotenv

load_dotenv()
client = genai.Client()


def generate_learning_content(lecture_text: str):
    prompt = f"""
    You are an expert university tutor. Analyze the following lecture text and create a highly structured, 6-level interactive quiz.
    
    CRITICAL INSTRUCTIONS: 
    1. You MUST generate at least 10 questions for EACH level.
    2. Randomize the True/False answers! DO NOT follow a predictable pattern (e.g., T, F, T, F). 
    
    Level 1: Free Recall (Short Answer) - Basic terminology. 1-3 words max.
    Level 2: Fill in the Blanks - Complete the sentence.
    Level 3: Multiple Choice (MCQ) - Conceptual understanding. 4 options.
    Level 4: True or False - Tricky nuances. Options must be exactly ["True", "False"].
    Level 5: Rearrange - Provide a complex sentence or process broken into 4-6 chunks in a RANDOMIZED order. The 'answer' must be the correctly ordered array.
    Level 6: Explain in Your Own Words - High-level synthesis. 2-3 sentence ideal answer.

    Respond ONLY with a valid JSON object in this exact format:
    {{
        "lesson_title": "Main Topic Name",
        "level_1_short_answer": [
            {{"prompt": "Question...", "answer": "Answer...", "type": "short_answer"}}
        ],
        "level_2_fill_blank": [
            {{"prompt": "Sentence with ____...", "answer": "word", "type": "fill_blank"}}
        ],
        "level_3_mcq": [
            {{"prompt": "Question...", "options": ["A", "B", "C", "D"], "answer": "Correct Option", "type": "multiple_choice"}}
        ],
        "level_4_true_false": [
            {{"prompt": "Statement...", "options": ["True", "False"], "answer": "True", "type": "true_false"}}
        ],
        "level_5_rearrange": [
            {{"prompt": "Order the steps of this process:", "chunks": ["Step 3", "Step 1", "Step 4", "Step 2"], "answer": ["Step 1", "Step 2", "Step 3", "Step 4"], "type": "rearrange"}}
        ],
        "level_6_explain": [
            {{"prompt": "Explain...", "answer": "Ideal explanation.", "type": "explain"}}
        ]
    }}

    Text to analyze:
    {lecture_text}
    """

    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
        )
        raw_text = response.text.strip()
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        clean_json_str = json_match.group(0) if json_match else raw_text
        return json.loads(clean_json_str)

    except Exception as e:
        print(f"AI Generation Error: {str(e)}")
        raise ValueError("AI failed to format the questions correctly.")
