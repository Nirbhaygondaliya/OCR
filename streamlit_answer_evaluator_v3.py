"""
Handwritten Answer Sheet Evaluator - Streamlit App
Powered by Claude API

Features:
- Evaluates ALL questions across all parts (Part A, B, C)
- Marks written directly on the PDF beside each answer
- Summary page at the end with all marks and suggestions
- Three evaluation modes: Standard, Strict, Range
- Consistent evaluation (same file = same results)
"""

import streamlit as st
import anthropic
import base64
import hashlib
import json
import re
from io import BytesIO
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics

# Page configuration
st.set_page_config(
    page_title="Answer Sheet Evaluator",
    page_icon="📝",
    layout="wide"
)

# Initialize cache for consistent evaluations
if 'evaluation_cache' not in st.session_state:
    st.session_state['evaluation_cache'] = {}

def get_file_hash(file_data: bytes, evaluation_mode: str, custom_criteria: str) -> str:
    """Generate a unique hash for the file + settings combination."""
    content = file_data + evaluation_mode.encode() + custom_criteria.encode()
    return hashlib.sha256(content).hexdigest()

def get_evaluation_prompt(mode: str) -> str:
    """Get the evaluation prompt based on the selected mode."""
    
    mode_instructions = {
        "standard": "Award marks fairly with partial credit. Focus on core concepts.",
        "strict": "High standards. Deduct for any errors, omissions, or unclear explanations.",
        "range": "Provide a mark RANGE (min-max) instead of single value, e.g., '6-8'."
    }
    
    prompt = f"""You are an expert examiner evaluating a handwritten answer sheet.

CRITICAL INSTRUCTIONS:
1. You MUST evaluate EVERY SINGLE QUESTION that has been attempted in this answer sheet
2. This appears to be an exam with multiple parts - evaluate ALL parts (Part A, Part B, Part C, etc.)
3. Look through ALL pages carefully - do not miss any questions
4. Questions may be numbered as Q.1, Q1, 1., प्र.1, etc. - identify all formats
5. Some questions may span multiple pages - evaluate the complete answer
6. If a question is NOT ATTEMPTED (blank/crossed out), mark it as "N.A." (Not Attempted)

EVALUATION MODE: {mode.upper()}
{mode_instructions[mode]}

IMPORTANT: Return your evaluation ONLY as a valid JSON object with this EXACT structure:

{{
    "exam_info": {{
        "total_parts": 3,
        "part_details": [
            {{"part": "A", "questions": "1-10", "marks_each": 3, "total": 30}},
            {{"part": "B", "questions": "11-16", "marks_each": 5, "total": 30}},
            {{"part": "C", "questions": "17-28", "marks_each": 10, "total": 90}}
        ]
    }},
    "questions": [
        {{
            "question_number": 1,
            "part": "A",
            "page_number": 4,
            "attempted": true,
            "student_answer_summary": "Brief summary of what student wrote",
            "marks_awarded": "{("2" if mode != "range" else "1-2")}",
            "max_marks": "3",
            "correct_points": ["Point 1 correct", "Point 2 correct"],
            "errors": ["Error 1", "Missing concept"],
            "brief_feedback": "One line feedback"
        }},
        {{
            "question_number": 2,
            "part": "A",
            "page_number": 4,
            "attempted": false,
            "student_answer_summary": "Not attempted",
            "marks_awarded": "0",
            "max_marks": "3",
            "correct_points": [],
            "errors": ["Question not attempted"],
            "brief_feedback": "Not attempted"
        }}
    ],
    "part_wise_summary": [
        {{"part": "A", "marks_obtained": "{("15" if mode != "range" else "12-18")}", "max_marks": "30", "questions_attempted": 10}},
        {{"part": "B", "marks_obtained": "{("18" if mode != "range" else "15-21")}", "max_marks": "30", "questions_attempted": 6}},
        {{"part": "C", "marks_obtained": "{("45" if mode != "range" else "40-50")}", "max_marks": "90", "questions_attempted": 9}}
    ],
    "total_marks_awarded": "{("78" if mode != "range" else "67-89")}",
    "total_max_marks": "150",
    "percentage": "{("52" if mode != "range" else "45-59")}",
    "overall_grade": "B",
    "overall_feedback": "2-3 sentences overall assessment",
    "missing_concepts": ["Key concept 1 missing", "Key concept 2 missing", "Key concept 3 missing"],
    "improvement_suggestions": ["Study suggestion 1", "Practice suggestion 2", "Focus area 3"],
    "strengths": ["Good point 1", "Good point 2"],
    "handwriting_notes": "Comment on legibility"
}}

CRITICAL RULES:
1. Include EVERY attempted question in the "questions" array - do not skip any
2. For questions not attempted, set "attempted": false and marks_awarded: "0"
3. Ensure question_number and page_number are accurate
4. The sum of all marks in part_wise_summary should equal total_marks_awarded
5. Return ONLY the JSON object, no other text
6. Ensure valid JSON format (double quotes, proper escaping)
7. Count all questions carefully - verify you haven't missed any
"""
    return prompt


def create_marks_overlay(evaluation_data: dict, page_width: float, page_height: float, page_num: int) -> BytesIO:
    """Create a transparent overlay PDF with marks for a specific page."""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Get questions for this page
    questions_on_page = [q for q in evaluation_data.get('questions', []) 
                        if q.get('page_number', 0) == page_num and q.get('attempted', True)]
    
    if questions_on_page:
        # Position marks in the right margin
        margin_x = page_width - 85
        y_position = page_height - 100
        
        for q in questions_on_page:
            if y_position < 80:
                # Reset position if too low
                y_position = page_height - 100
                margin_x -= 95
            
            # Draw mark box
            box_width = 75
            box_height = 50
            
            # Background box - light red/pink
            c.setFillColor(colors.Color(1, 0.85, 0.85, alpha=0.95))
            c.setStrokeColor(colors.Color(0.8, 0, 0))
            c.setLineWidth(2)
            c.roundRect(margin_x - 5, y_position - 35, box_width, box_height, 5, fill=1, stroke=1)
            
            # Question number and Part
            c.setFillColor(colors.Color(0.8, 0, 0))
            c.setFont("Helvetica-Bold", 9)
            part = q.get('part', '')
            q_num = q.get('question_number', '?')
            c.drawString(margin_x, y_position + 5, f"Q{q_num}")
            
            # Marks - larger font
            c.setFont("Helvetica-Bold", 16)
            marks_text = f"{q.get('marks_awarded', '?')}/{q.get('max_marks', '?')}"
            c.drawString(margin_x, y_position - 20, marks_text)
            
            y_position -= 70
    
    c.save()
    packet.seek(0)
    return packet


def create_summary_page(evaluation_data: dict, mode: str) -> BytesIO:
    """Create a comprehensive summary page PDF."""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    width, height = A4
    
    # Colors
    header_color = colors.Color(0.1, 0.2, 0.5)
    accent_color = colors.Color(0.7, 0.1, 0.1)
    green_color = colors.Color(0.1, 0.5, 0.1)
    
    y = height - 40
    
    # Title
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, y, "EVALUATION SUMMARY REPORT")
    y -= 8
    
    # Underline
    c.setStrokeColor(accent_color)
    c.setLineWidth(2)
    c.line(80, y, width - 80, y)
    y -= 25
    
    # Mode indicator
    mode_labels = {"standard": "Standard", "strict": "Strict", "range": "Range (Min-Max)"}
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.gray)
    c.drawString(50, y, f"Evaluation Mode: {mode_labels.get(mode, mode)}")
    y -= 25
    
    # Total Score Box
    c.setFillColor(colors.Color(0.95, 0.95, 1))
    c.setStrokeColor(header_color)
    c.setLineWidth(2)
    c.roundRect(50, y - 55, width - 100, 60, 8, fill=1, stroke=1)
    
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2, y - 12, "TOTAL SCORE")
    
    c.setFont("Helvetica-Bold", 26)
    c.setFillColor(accent_color)
    total_text = f"{evaluation_data.get('total_marks_awarded', '?')} / {evaluation_data.get('total_max_marks', '?')}"
    c.drawCentredString(width/2, y - 40, total_text)
    
    # Percentage and Grade
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.black)
    percentage = evaluation_data.get('percentage', '?')
    grade = evaluation_data.get('overall_grade', '')
    c.drawCentredString(width/2, y - 58, f"Percentage: {percentage}%   |   Grade: {grade}")
    
    y -= 85
    
    # Part-wise Summary Table
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "PART-WISE BREAKDOWN")
    y -= 5
    c.setStrokeColor(header_color)
    c.setLineWidth(1)
    c.line(50, y, 220, y)
    y -= 18
    
    # Table header
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(colors.white)
    c.setFillColor(header_color)
    c.rect(50, y - 3, width - 100, 15, fill=1)
    c.setFillColor(colors.white)
    c.drawString(55, y, "Part")
    c.drawString(120, y, "Marks Obtained")
    c.drawString(220, y, "Max Marks")
    c.drawString(310, y, "Questions")
    c.drawString(400, y, "Percentage")
    y -= 18
    
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.black)
    
    for part_summary in evaluation_data.get('part_wise_summary', []):
        part = part_summary.get('part', '?')
        obtained = part_summary.get('marks_obtained', '?')
        max_m = part_summary.get('max_marks', '?')
        attempted = part_summary.get('questions_attempted', '?')
        
        # Calculate percentage for this part
        try:
            if '-' in str(obtained):  # Range mode
                part_pct = "N/A"
            else:
                part_pct = f"{(float(obtained)/float(max_m))*100:.0f}%"
        except:
            part_pct = "N/A"
        
        c.drawString(55, y, f"Part {part}")
        c.drawString(120, y, str(obtained))
        c.drawString(220, y, str(max_m))
        c.drawString(310, y, str(attempted))
        c.drawString(400, y, part_pct)
        y -= 14
    
    y -= 15
    
    # Question-wise breakdown (compact)
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "QUESTION-WISE MARKS")
    y -= 5
    c.line(50, y, 200, y)
    y -= 15
    
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    
    # Display questions in columns
    questions = evaluation_data.get('questions', [])
    col_width = 180
    start_x = 50
    col = 0
    row_height = 12
    start_y = y
    max_rows_per_col = 15
    row_count = 0
    
    for q in questions:
        q_num = q.get('question_number', '?')
        marks = q.get('marks_awarded', '?')
        max_marks = q.get('max_marks', '?')
        attempted = q.get('attempted', True)
        
        x_pos = start_x + (col * col_width)
        
        if attempted:
            c.setFillColor(colors.black)
            text = f"Q{q_num}: {marks}/{max_marks}"
        else:
            c.setFillColor(colors.gray)
            text = f"Q{q_num}: N.A."
        
        # Truncate feedback
        feedback = q.get('brief_feedback', '')[:35]
        c.drawString(x_pos, y, f"{text} - {feedback}")
        
        row_count += 1
        y -= row_height
        
        if row_count >= max_rows_per_col:
            col += 1
            row_count = 0
            y = start_y
            if col >= 3:
                break
    
    y = start_y - (min(len(questions), max_rows_per_col) * row_height) - 15
    
    # Strengths Section
    if y > 250:
        c.setFillColor(green_color)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "STRENGTHS")
        y -= 5
        c.setStrokeColor(green_color)
        c.line(50, y, 130, y)
        y -= 14
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        for strength in evaluation_data.get('strengths', [])[:3]:
            c.drawString(55, y, f"✓ {strength[:70]}")
            y -= 12
        y -= 8
    
    # Missing Concepts Section
    if y > 180:
        c.setFillColor(accent_color)
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "MISSING CONCEPTS / AREAS TO IMPROVE")
        y -= 5
        c.setStrokeColor(accent_color)
        c.line(50, y, 280, y)
        y -= 14
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        for concept in evaluation_data.get('missing_concepts', [])[:5]:
            c.drawString(55, y, f"• {concept[:75]}")
            y -= 12
        y -= 8
    
    # Improvement Suggestions
    if y > 100:
        c.setFillColor(colors.Color(0, 0.4, 0.6))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, "SUGGESTIONS FOR IMPROVEMENT")
        y -= 5
        c.setStrokeColor(colors.Color(0, 0.4, 0.6))
        c.line(50, y, 250, y)
        y -= 14
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 9)
        for i, suggestion in enumerate(evaluation_data.get('improvement_suggestions', [])[:4], 1):
            c.drawString(55, y, f"{i}. {suggestion[:75]}")
            y -= 12
    
    # Overall Feedback at bottom
    if y > 60:
        y -= 10
        c.setFillColor(header_color)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(50, y, "Overall Assessment:")
        y -= 12
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Oblique", 9)
        feedback = evaluation_data.get('overall_feedback', '')[:200]
        
        # Simple word wrap
        words = feedback.split()
        line = ""
        for word in words:
            if len(line + word) < 90:
                line += word + " "
            else:
                c.drawString(55, y, line.strip())
                y -= 11
                line = word + " "
        if line:
            c.drawString(55, y, line.strip())
    
    # Footer
    c.setFillColor(colors.gray)
    c.setFont("Helvetica", 7)
    c.drawCentredString(width/2, 25, "Generated by Answer Sheet Evaluator | Powered by Claude AI")
    
    c.save()
    packet.seek(0)
    return packet


def create_marked_pdf(original_pdf_bytes: bytes, evaluation_data: dict, mode: str) -> bytes:
    """Create the final PDF with marks overlay and summary page."""
    
    # Read original PDF
    original_reader = PdfReader(BytesIO(original_pdf_bytes))
    writer = PdfWriter()
    
    # Process each page
    for page_num, page in enumerate(original_reader.pages, 1):
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        
        # Create overlay for this page
        overlay_packet = create_marks_overlay(evaluation_data, page_width, page_height, page_num)
        overlay_reader = PdfReader(overlay_packet)
        
        if len(overlay_reader.pages) > 0:
            overlay_page = overlay_reader.pages[0]
            page.merge_page(overlay_page)
        
        writer.add_page(page)
    
    # Add summary page at the end
    summary_packet = create_summary_page(evaluation_data, mode)
    summary_reader = PdfReader(summary_packet)
    for summary_page in summary_reader.pages:
        writer.add_page(summary_page)
    
    # Write final PDF
    output_buffer = BytesIO()
    writer.write(output_buffer)
    output_buffer.seek(0)
    
    return output_buffer.getvalue()


def parse_json_response(response_text: str) -> dict:
    """Parse JSON from Claude's response, handling potential issues."""
    text = response_text.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Find JSON object
    start = text.find('{')
    end = text.rfind('}') + 1
    
    if start != -1 and end > start:
        json_str = text[start:end]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            st.error(f"JSON parsing error: {e}")
            # Try to fix common issues
            json_str = json_str.replace("'", '"')
            json_str = re.sub(r',\s*}', '}', json_str)  # Remove trailing commas
            json_str = re.sub(r',\s*]', ']', json_str)
            try:
                return json.loads(json_str)
            except:
                pass
    
    return None


# Title and description
st.title("📝 Handwritten Answer Sheet Evaluator")
st.markdown("##### Upload answer sheet → Get marked PDF with complete evaluation")
st.markdown("---")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "Anthropic API Key:",
        type="password",
        help="Your API key is not stored"
    )
    
    st.markdown("---")
    
    st.header("📊 Evaluation Mode")
    evaluation_mode = st.radio(
        "Select mode:",
        options=["standard", "strict", "range"],
        format_func=lambda x: {
            "standard": "📗 Standard",
            "strict": "📕 Strict",
            "range": "📘 Range"
        }[x]
    )
    
    mode_info = {
        "standard": "Balanced with partial credit",
        "strict": "High standards, precise",
        "range": "Min-max mark range"
    }
    st.caption(mode_info[evaluation_mode])
    
    st.markdown("---")
    
    if st.button("🗑️ Clear Cache"):
        st.session_state['evaluation_cache'] = {}
        if 'marked_pdf' in st.session_state:
            del st.session_state['marked_pdf']
        st.success("Cleared!")
        st.rerun()

# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📤 Upload Answer Sheet")
    
    uploaded_file = st.file_uploader(
        "Choose PDF file",
        type=['pdf'],
        help="Upload complete answer sheet"
    )
    
    custom_criteria = ""
    
    if uploaded_file:
        st.success(f"✓ {uploaded_file.name}")
        st.info(f"Size: {len(uploaded_file.getvalue()):,} bytes")
        
        with st.expander("🎯 Custom Marking Scheme (Optional)"):
            custom_criteria = st.text_area(
                "Enter marking scheme:",
                placeholder="Part A: Q1-10 (3 marks each)\nPart B: Q11-16 (5 marks each)\nPart C: Q17-28 (10 marks each)",
                height=100
            )

with col2:
    st.header("📥 Download Marked PDF")
    
    if uploaded_file and api_key:
        file_data = uploaded_file.getvalue()
        file_hash = get_file_hash(file_data, evaluation_mode, custom_criteria)
        
        is_cached = file_hash in st.session_state['evaluation_cache']
        
        if is_cached:
            st.info("💾 Cached result available")
        
        button_text = "📋 Load Cached" if is_cached else "🚀 Evaluate All Questions"
        
        if st.button(button_text, type="primary", use_container_width=True):
            
            if is_cached:
                cached = st.session_state['evaluation_cache'][file_hash]
                st.session_state['marked_pdf'] = cached['marked_pdf']
                st.session_state['filename'] = cached['filename']
                st.session_state['eval_data'] = cached.get('eval_data', {})
                st.success("✓ Loaded!")
            else:
                with st.spinner("Analyzing ALL questions... (60-90 seconds)"):
                    try:
                        client = anthropic.Anthropic(api_key=api_key)
                        
                        pdf_data = base64.standard_b64encode(file_data).decode('utf-8')
                        
                        prompt = get_evaluation_prompt(evaluation_mode)
                        if custom_criteria:
                            prompt += f"\n\nMARKING SCHEME PROVIDED:\n{custom_criteria}"
                        
                        message = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=16000,  # Increased for more questions
                            temperature=0,
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "document",
                                            "source": {
                                                "type": "base64",
                                                "media_type": "application/pdf",
                                                "data": pdf_data
                                            }
                                        },
                                        {
                                            "type": "text",
                                            "text": prompt
                                        }
                                    ]
                                }
                            ]
                        )
                        
                        response_text = message.content[0].text
                        evaluation_data = parse_json_response(response_text)
                        
                        if evaluation_data:
                            # Validate we got all questions
                            num_questions = len(evaluation_data.get('questions', []))
                            st.info(f"Evaluated {num_questions} questions")
                            
                            marked_pdf = create_marked_pdf(file_data, evaluation_data, evaluation_mode)
                            
                            st.session_state['marked_pdf'] = marked_pdf
                            st.session_state['filename'] = uploaded_file.name
                            st.session_state['eval_data'] = evaluation_data
                            
                            st.session_state['evaluation_cache'][file_hash] = {
                                'marked_pdf': marked_pdf,
                                'filename': uploaded_file.name,
                                'eval_data': evaluation_data
                            }
                            
                            st.success(f"✓ PDF generated with {num_questions} questions evaluated!")
                        else:
                            st.error("Failed to parse evaluation")
                            with st.expander("Debug: Raw Response"):
                                st.code(response_text[:2000])
                            
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    
    elif not uploaded_file:
        st.info("👆 Upload a PDF")
    elif not api_key:
        st.warning("⚠️ Enter API key")

# Download section
if 'marked_pdf' in st.session_state:
    st.markdown("---")
    
    # Show summary stats
    if 'eval_data' in st.session_state:
        eval_data = st.session_state['eval_data']
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            st.metric("Total Score", f"{eval_data.get('total_marks_awarded', '?')}/{eval_data.get('total_max_marks', '?')}")
        with col_b:
            st.metric("Percentage", f"{eval_data.get('percentage', '?')}%")
        with col_c:
            st.metric("Questions Evaluated", len(eval_data.get('questions', [])))
    
    filename = st.session_state.get('filename', 'answer_sheet').replace('.pdf', '')
    
    st.download_button(
        label="📥 DOWNLOAD MARKED PDF",
        data=st.session_state['marked_pdf'],
        file_name=f"{filename}_evaluated.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary"
    )
    
    st.caption("✓ Marks on each answer + Complete summary page at end")

# Footer
st.markdown("---")
st.caption("Made with ❤️ using Claude AI | Evaluates ALL questions consistently")
