from flask import Flask, render_template, request, session, redirect, url_for
import google.generativeai as genai
import ast
import os
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Gemini API Configuration
API_KEY = "Enter your API-KEY"
genai.configure(api_key=API_KEY)
MODEL_NAME = "models/gemini-1.5-flash"

# In-memory user store (replace with database later)
users = {}

def format_as_bullets(text):
    text = re.sub(r'\*\*|\*', '', text)
    lines = text.split('\n')
    formatted = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(\d+\.\s|[-•]\s)", line):
            formatted.append(line)
        else:
            formatted.append(f"- {line}")
    return '<br>'.join(formatted)

# === Agent Classes ===
class BaseAgent:
    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME)

    def respond(self, prompt):
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            return f"Error generating response: {e}"

class CoachAgent(BaseAgent):
    def respond(self, query, student_id=None):
        prompt = f"""
Hey {student_id}, let's talk about "{query}" in a fun and motivating way!
Please explain in simple bullet points or numbered list for easy understanding.
"""
        return super().respond(prompt)

class TutorAgent(BaseAgent):
    def respond(self, query, student_id=None):
        prompt = f"""
Explain the following concept in detail: "{query}".
Respond using bullet points or numbered list for clarity.
"""
        return super().respond(prompt)

class LearningTrackingAgent(BaseAgent):
    def respond(self, query, student_id=None):
        prompt = f'''
Generate a list of exactly 10 multiple-choice questions about the topic "{query}".
Respond with ONLY valid Python code (no explanation or markdown), in this format:

[
    {{
        "question": "What is ...?",
        "options": {{
            "A": "...",
            "B": "...",
            "C": "...",
            "D": "..."
        }},
        "answer": "C"
    }},
    ...
]
'''
        return super().respond(prompt)

class RoadmapAgent(BaseAgent):
    def respond(self, query, student_id=None):
        prompt = f"""
Create a learning roadmap for "{query}".
Respond using numbered steps or bullet points to outline the learning path.
"""
        return super().respond(prompt)

class MasterAgent:
    def __init__(self):
        self.model = genai.GenerativeModel(MODEL_NAME)

    def get_agent(self, query):
        prompt = f'''
Decide the best agent for the following query:
"{query}"

Agents:
1. CoachAgent: For motivational, simple explanations.
2. TutorAgent: For in-depth academic explanations.
3. LearningTrackingAgent: For quizzes, progress checks, or practice.
4. RoadmapAgent: For curriculum guidance or learning plans.

Respond ONLY with the agent name.
'''
        try:
            response = self.model.generate_content(prompt)
            agent_name = response.text.strip()
            if agent_name in ["CoachAgent", "TutorAgent", "LearningTrackingAgent", "RoadmapAgent"]:
                return agent_name
            return "CoachAgent"
        except Exception as e:
            return "CoachAgent"

# ==== Authentication ====

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        student_id = request.form['student_id']
        password = request.form['password']
        if student_id in users:
            return render_template("signup.html", error="Student ID already exists.")
        users[student_id] = password
        session['student_id'] = student_id
        return redirect(url_for("home"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        student_id = request.form['student_id']
        password = request.form['password']
        if users.get(student_id) == password:
            session['student_id'] = student_id
            return redirect(url_for("home"))
        return render_template("login.html", error="Invalid ID or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ==== Routes ====

@app.route("/")
def home():
    if 'student_id' not in session:
        return redirect(url_for('login'))
    return render_template("index.html")

@app.route("/ask", methods=["POST"])
def ask():
    if 'student_id' not in session:
        return redirect(url_for("login"))

    query = request.form.get("query")
    student_id = session.get("student_id")

    master_agent = MasterAgent()
    agent_name = master_agent.get_agent(query)

    if agent_name == "LearningTrackingAgent":
        session['topic'] = query
        response = LearningTrackingAgent().respond(query, student_id)
        cleaned = response.strip()

        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = "\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```"))

        try:
            quiz_data = ast.literal_eval(cleaned)
            session['quiz_questions'] = quiz_data
            session['score'] = 0
            session['q_index'] = 0
            session['wrong_answers'] = []
            return redirect(url_for('quiz'))
        except Exception as e:
            return f"Failed to load quiz: {e}<br><pre>{cleaned}</pre>"

    if agent_name == "CoachAgent":
        response = CoachAgent().respond(query, student_id)
    elif agent_name == "TutorAgent":
        response = TutorAgent().respond(query, student_id)
    elif agent_name == "RoadmapAgent":
        response = RoadmapAgent().respond(query, student_id)
    else:
        response = "Unknown agent assigned."

    response = format_as_bullets(response)
    return render_template("response.html", agent=agent_name, response=response)

@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    if 'student_id' not in session:
        return redirect(url_for("login"))

    questions = session.get('quiz_questions', [])
    q_index = session.get('q_index', 0)

    if 'score' not in session:
        session['score'] = 0
    if 'submitted' not in session:
        session['submitted'] = False
    if 'wrong_answers' not in session:
        session['wrong_answers'] = []

    if request.method == "POST":
        if "submit" in request.form:
            selected = request.form.get("option")
            correct = questions[q_index]['answer']
            if selected == correct:
                session['feedback'] = "Correct!"
                session['score'] += 1
            else:
                session['feedback'] = f"Incorrect. Correct answer is {correct}."
                session['wrong_answers'].append({
                    "question": questions[q_index]['question'],
                    "correct": correct,
                    "options": questions[q_index]['options']
                })
            session['submitted'] = True
        elif "next" in request.form:
            session['q_index'] = q_index + 1
            session['feedback'] = None
            session['submitted'] = False
            return redirect(url_for("quiz"))

    if q_index < len(questions):
        question = questions[q_index]
        return render_template(
            "quiz.html",
            question=question['question'],
            options=question['options'],
            q_number=q_index + 1,
            total=len(questions),
            feedback=session.get('feedback'),
            submitted=session.get('submitted'),
            topic=session.get('topic')
        )
    else:
        return render_template(
            "result.html",
            score=session['score'],
            total=len(questions),
            wrong_answers=session.get('wrong_answers', []),
            topic=session.get('topic')
        )

if __name__ == "__main__":
    app.run(debug=True)
