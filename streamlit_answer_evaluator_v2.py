"""
Handwritten Answer Sheet Evaluator - Streamlit App
Powered by Claude API

Features:
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
from reportlab.pdfbase.ttfonts import TTFont

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
    
    prompt = f"""Analyze this handwritten answer sheet PDF and evaluate each answer.

EVALUATION MODE: {mode.upper()}
{mode_instructions[mode]}

IMPORTANT: Return your evaluation ONLY as a valid JSON object with this exact structure:
{{
    "questions": [
        {{
            "question_number": 1,
            "page_number": 1,
            "student_answer_summary": "Brief summary of what student wrote",
            "marks_awarded": "{("7" if mode != "range" else "6-8")}",
            "max_marks": "10",
            "correct_points": ["Point 1 that was correct", "Point 2 that was correct"],
            "errors": ["Error or mistake 1", "Missing concept 2"],
            "brief_feedback": "One line feedback"
        }}
    ],
    "total_marks_awarded": "{("35" if mode != "range" else "32-38")}",
    "total_max_marks": "50",
    "percentage": "{("70" if mode != "range" else "64-76")}",
    "overall_feedback": "2-3 sentences overall assessment",
    "missing_concepts": ["List of key concepts student missed across all answers"],
    "improvement_suggestions": ["Specific suggestion 1", "Specific suggestion 2", "Study recommendation"],
    "handwriting_notes": "Comment on legibility if relevant"
}}

Rules:
1. Identify ALL questions/answers in the document
2. For each answer, evaluate correctness and assign marks
3. Be specific about what's correct and what's missing
4. Return ONLY the JSON object, no other text before or after
5. Ensure valid JSON format (use double quotes, escape special characters)
"""
    return prompt


def create_marks_overlay(evaluation_data: dict, page_width: float, page_height: float, page_num: int) -> BytesIO:
    """Create a transparent overlay PDF with marks for a specific page."""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(page_width, page_height))
    
    # Get questions for this page
    questions_on_page = [q for q in evaluation_data.get('questions', []) 
                        if q.get('page_number', 1) == page_num]
    
    if questions_on_page:
        # Position marks in the right margin
        margin_x = page_width - 80
        y_position = page_height - 60
        
        for q in questions_on_page:
            # Draw a box for marks
            box_width = 70
            box_height = 40
            
            # Red box background
            c.setFillColor(colors.Color(1, 0.9, 0.9, alpha=0.9))
            c.setStrokeColor(colors.red)
            c.setLineWidth(2)
            c.roundRect(margin_x - 5, y_position - 30, box_width, box_height, 5, fill=1, stroke=1)
            
            # Question number
            c.setFillColor(colors.red)
            c.setFont("Helvetica-Bold", 10)
            c.drawString(margin_x, y_position, f"Q{q.get('question_number', '?')}")
            
            # Marks
            c.setFont("Helvetica-Bold", 14)
            marks_text = f"{q.get('marks_awarded', '?')}/{q.get('max_marks', '?')}"
            c.drawString(margin_x, y_position - 20, marks_text)
            
            y_position -= 70  # Space between questions
            
            if y_position < 100:  # Reset if we're near bottom
                y_position = page_height - 60
                margin_x -= 90  # Move to next column
    
    c.save()
    packet.seek(0)
    return packet


def create_summary_page(evaluation_data: dict, mode: str) -> BytesIO:
    """Create a summary page PDF with all marks and suggestions."""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    width, height = A4
    
    # Colors
    header_color = colors.Color(0.2, 0.3, 0.5)
    accent_color = colors.Color(0.8, 0.2, 0.2)
    
    y = height - 50
    
    # Title
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(width/2, y, "EVALUATION SUMMARY")
    y -= 10
    
    # Underline
    c.setStrokeColor(accent_color)
    c.setLineWidth(3)
    c.line(100, y, width - 100, y)
    y -= 40
    
    # Mode indicator
    mode_labels = {"standard": "Standard", "strict": "Strict", "range": "Range (Min-Max)"}
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.gray)
    c.drawString(50, y, f"Evaluation Mode: {mode_labels.get(mode, mode)}")
    y -= 30
    
    # Total Score Box
    c.setFillColor(colors.Color(0.95, 0.95, 1))
    c.setStrokeColor(header_color)
    c.setLineWidth(2)
    c.roundRect(50, y - 60, width - 100, 70, 10, fill=1, stroke=1)
    
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, y - 15, "TOTAL SCORE")
    
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(accent_color)
    total_text = f"{evaluation_data.get('total_marks_awarded', '?')} / {evaluation_data.get('total_max_marks', '?')}"
    c.drawCentredString(width/2, y - 45, total_text)
    
    # Percentage
    c.setFont("Helvetica", 14)
    c.setFillColor(colors.black)
    percentage = evaluation_data.get('percentage', '?')
    c.drawCentredString(width/2, y - 70, f"({percentage}%)")
    
    y -= 110
    
    # Question-wise breakdown
    c.setFillColor(header_color)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "QUESTION-WISE MARKS")
    y -= 5
    c.setStrokeColor(header_color)
    c.setLineWidth(1)
    c.line(50, y, 250, y)
    y -= 20
    
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.black)
    
    for q in evaluation_data.get('questions', []):
        q_num = q.get('question_number', '?')
        marks = q.get('marks_awarded', '?')
        max_marks = q.get('max_marks', '?')
        feedback = q.get('brief_feedback', '')[:60]  # Truncate long feedback
        
        c.setFont("Helvetica-Bold", 11)
        c.drawString(60, y, f"Q{q_num}:")
        c.setFont("Helvetica", 11)
        c.drawString(90, y, f"{marks}/{max_marks}")
        c.setFillColor(colors.gray)
        c.setFont("Helvetica", 9)
        c.drawString(140, y, f"- {feedback}")
        c.setFillColor(colors.black)
        y -= 18
        
        if y < 300:  # Leave room for suggestions
            break
    
    y -= 20
    
    # Missing Concepts Section
    c.setFillColor(accent_color)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "MISSING CONCEPTS / POINTS")
    y -= 5
    c.setStrokeColor(accent_color)
    c.line(50, y, 280, y)
    y -= 18
    
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    
    missing = evaluation_data.get('missing_concepts', [])
    for i, concept in enumerate(missing[:6], 1):  # Max 6 items
        concept_text = concept[:70] if len(concept) > 70 else concept
        c.drawString(60, y, f"• {concept_text}")
        y -= 15
    
    y -= 15
    
    # Improvement Suggestions
    c.setFillColor(colors.Color(0.1, 0.5, 0.1))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, "SUGGESTIONS FOR IMPROVEMENT")
    y -= 5
    c.setStrokeColor(colors.Color(0.1, 0.5, 0.1))
    c.line(50, y, 300, y)
    y -= 18
    
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 10)
    
    suggestions = evaluation_data.get('improvement_suggestions', [])
    for i, suggestion in enumerate(suggestions[:5], 1):  # Max 5 items
        suggestion_text = suggestion[:80] if len(suggestion) > 80 else suggestion
        c.drawString(60, y, f"{i}. {suggestion_text}")
        y -= 15
    
    y -= 15
    
    # Overall Feedback
    if y > 80:
        c.setFillColor(header_color)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Overall Assessment:")
        y -= 15
        
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Oblique", 10)
        feedback = evaluation_data.get('overall_feedback', '')
        
        # Word wrap the feedback
        words = feedback.split()
        line = ""
        for word in words:
            if len(line + word) < 80:
                line += word + " "
            else:
                c.drawString(60, y, line.strip())
                y -= 14
                line = word + " "
        if line:
            c.drawString(60, y, line.strip())
    
    # Footer
    c.setFillColor(colors.gray)
    c.setFont("Helvetica", 8)
    c.drawCentredString(width/2, 30, "Generated by Answer Sheet Evaluator | Powered by Claude AI")
    
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
    # Try to find JSON in the response
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
            try:
                return json.loads(json_str)
            except:
                pass
    
    return None


# Title and description
st.title("📝 Handwritten Answer Sheet Evaluator")
st.markdown("##### Upload your answer sheet → Get marked PDF with summary")
st.markdown("---")

# Sidebar for settings
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "Anthropic API Key:",
        type="password",
        help="Your API key will not be stored"
    )
    
    st.markdown("---")
    
    # Evaluation Mode Selection
    st.header("📊 Evaluation Mode")
    evaluation_mode = st.radio(
        "Select mode:",
        options=["standard", "strict", "range"],
        format_func=lambda x: {
            "standard": "📗 Standard",
            "strict": "📕 Strict",
            "range": "📘 Range (Min-Max)"
        }[x]
    )
    
    mode_info = {
        "standard": "Balanced evaluation with partial credit",
        "strict": "High standards, precise marking",
        "range": "Provides min-max mark range"
    }
    st.caption(mode_info[evaluation_mode])
    
    st.markdown("---")
    
    # Clear cache button
    if st.button("🗑️ Clear Cache"):
        st.session_state['evaluation_cache'] = {}
        if 'marked_pdf' in st.session_state:
            del st.session_state['marked_pdf']
        st.success("Cache cleared!")
        st.rerun()

# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📤 Upload Answer Sheet")
    
    uploaded_file = st.file_uploader(
        "Choose PDF file",
        type=['pdf'],
        help="Upload handwritten answer sheet"
    )
    
    custom_criteria = ""
    
    if uploaded_file:
        st.success(f"✓ {uploaded_file.name}")
        
        with st.expander("🎯 Custom Criteria (Optional)"):
            custom_criteria = st.text_area(
                "Answer key or criteria:",
                placeholder="Q1: Photosynthesis (10 marks)\nQ2: Newton's laws (10 marks)",
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
        
        button_text = "📋 Load Cached Result" if is_cached else "🚀 Evaluate & Generate PDF"
        
        if st.button(button_text, type="primary", use_container_width=True):
            
            if is_cached:
                cached = st.session_state['evaluation_cache'][file_hash]
                st.session_state['marked_pdf'] = cached['marked_pdf']
                st.session_state['filename'] = cached['filename']
                st.success("✓ Loaded from cache!")
            else:
                with st.spinner("Analyzing... This may take 30-60 seconds..."):
                    try:
                        client = anthropic.Anthropic(api_key=api_key)
                        
                        pdf_data = base64.standard_b64encode(file_data).decode('utf-8')
                        
                        prompt = get_evaluation_prompt(evaluation_mode)
                        if custom_criteria:
                            prompt += f"\n\nAdditional Criteria:\n{custom_criteria}"
                        
                        # Call Claude API
                        message = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=8000,
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
                        
                        # Parse evaluation data
                        evaluation_data = parse_json_response(response_text)
                        
                        if evaluation_data:
                            # Generate marked PDF
                            marked_pdf = create_marked_pdf(file_data, evaluation_data, evaluation_mode)
                            
                            st.session_state['marked_pdf'] = marked_pdf
                            st.session_state['filename'] = uploaded_file.name
                            
                            # Cache the result
                            st.session_state['evaluation_cache'][file_hash] = {
                                'marked_pdf': marked_pdf,
                                'filename': uploaded_file.name
                            }
                            
                            st.success("✓ PDF generated!")
                        else:
                            st.error("Failed to parse evaluation. Please try again.")
                            st.text("Raw response:")
                            st.code(response_text[:500])
                            
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    
    elif not uploaded_file:
        st.info("👆 Upload a PDF to begin")
    elif not api_key:
        st.warning("⚠️ Enter API key in sidebar")

# Download section
if 'marked_pdf' in st.session_state:
    st.markdown("---")
    
    filename = st.session_state.get('filename', 'answer_sheet').replace('.pdf', '')
    
    st.download_button(
        label="📥 DOWNLOAD MARKED PDF",
        data=st.session_state['marked_pdf'],
        file_name=f"{filename}_evaluated.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary"
    )
    
    st.caption("PDF includes marks on each answer + summary page at the end")

# Footer
st.markdown("---")
st.caption("Made with ❤️ using Claude API | Same file = Same results")
