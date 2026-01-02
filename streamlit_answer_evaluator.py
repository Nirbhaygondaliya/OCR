"""
Handwritten Answer Sheet Evaluator - Streamlit App
Powered by Claude API

Features:
- Consistent evaluation (same file = same results)
- Three evaluation modes: Standard, Strict, Range
- Marks displayed on answer area with summary page
"""

import streamlit as st
import anthropic
import base64
import hashlib
from io import BytesIO

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
    
    base_instructions = """Please carefully evaluate this handwritten answer sheet PDF.

IMPORTANT: Format your evaluation in TWO distinct sections:

═══════════════════════════════════════════════════════════════════════════════
SECTION 1: ANSWER-BY-ANSWER EVALUATION (Marks on Answer Area)
═══════════════════════════════════════════════════════════════════════════════

For each question/answer found in the document, provide:

┌─────────────────────────────────────────────────────────────────────────────┐
│ QUESTION [X]                                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Student's Answer (Transcribed):                                              │
│ [Write what the student wrote]                                               │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ MARKS AWARDED: [X]/[Total] {marks_format}                               │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│ Evaluation:                                                                  │
│ ✓ Correct Points: [List what's correct]                                      │
│ ✗ Errors/Issues: [List any mistakes]                                         │
│ Handwriting: [Legibility assessment if applicable]                           │
└─────────────────────────────────────────────────────────────────────────────┘

Repeat this box format for EACH question found.

═══════════════════════════════════════════════════════════════════════════════
SECTION 2: SUMMARY PAGE - MISSING POINTS & SUGGESTIONS
═══════════════════════════════════════════════════════════════════════════════

This section should be like a separate page at the end with:

╔═════════════════════════════════════════════════════════════════════════════╗
║                         EVALUATION SUMMARY                                    ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  OVERALL SCORE: [Total Marks] / [Maximum Marks] = [Percentage]%              ║
║                                                                               ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                         MISSING POINTS BY QUESTION                           ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Question 1:                                                                  ║
║  • [Missing concept/point 1]                                                  ║
║  • [Missing concept/point 2]                                                  ║
║                                                                               ║
║  Question 2:                                                                  ║
║  • [Missing concept/point 1]                                                  ║
║  (Repeat for all questions)                                                   ║
║                                                                               ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                         SUGGESTIONS FOR IMPROVEMENT                          ║
╠═════════════════════════════════════════════════════════════════════════════╣
║                                                                               ║
║  Content Suggestions:                                                         ║
║  1. [Specific suggestion to improve answers]                                  ║
║  2. [Another suggestion]                                                      ║
║                                                                               ║
║  Presentation Suggestions:                                                    ║
║  1. [Handwriting/organization suggestion]                                     ║
║  2. [Another suggestion]                                                      ║
║                                                                               ║
║  Study Recommendations:                                                       ║
║  • [Topics to review]                                                         ║
║  • [Resources or methods to try]                                              ║
║                                                                               ║
╚═════════════════════════════════════════════════════════════════════════════╝
"""

    if mode == "standard":
        mode_specific = """
EVALUATION MODE: STANDARD
- Award marks fairly based on understanding demonstrated
- Partial credit for partially correct answers
- Focus on core concepts being correct
- Minor errors or omissions have small deductions
- Marks format: Single value (e.g., 7/10)
"""
        marks_format = "(Single value, e.g., 7/10)"
        
    elif mode == "strict":
        mode_specific = """
EVALUATION MODE: STRICT
- Evaluate with high standards and precision
- Require complete and accurate answers for full marks
- Deduct marks for any errors, omissions, or unclear explanations
- Spelling and presentation matter
- No partial credit for vague or incomplete answers
- Marks format: Single value with strict deductions (e.g., 5/10)
"""
        marks_format = "(Strict scoring, e.g., 5/10)"
        
    elif mode == "range":
        mode_specific = """
EVALUATION MODE: RANGE
- Provide a mark RANGE instead of a single value
- Lower bound: Minimum marks (strict interpretation)
- Upper bound: Maximum marks (generous interpretation)
- This accounts for subjectivity in evaluation
- Marks format: Range (e.g., 6-8/10)
"""
        marks_format = "(Range format, e.g., 6-8/10)"
    
    else:
        mode_specific = ""
        marks_format = ""
    
    return base_instructions.replace("{marks_format}", marks_format) + mode_specific


# Title and description
st.title("📝 Handwritten Answer Sheet Evaluator")
st.markdown("### Powered by Claude AI")
st.markdown("---")

# Sidebar for API key and settings
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input(
        "Enter your Anthropic API Key:",
        type="password",
        help="Your API key will not be stored"
    )
    
    st.markdown("---")
    
    # Evaluation Mode Selection
    st.header("📊 Evaluation Mode")
    evaluation_mode = st.radio(
        "Select evaluation strictness:",
        options=["standard", "strict", "range"],
        format_func=lambda x: {
            "standard": "📗 Standard - Balanced evaluation",
            "strict": "📕 Strict - High standards, precise marking",
            "range": "📘 Range - Min-Max mark range"
        }[x],
        help="Choose how strictly answers should be evaluated"
    )
    
    # Mode descriptions
    mode_descriptions = {
        "standard": "**Standard Mode**: Fair evaluation with partial credit. Focuses on understanding core concepts.",
        "strict": "**Strict Mode**: High standards with precise marking. Deductions for any errors or omissions.",
        "range": "**Range Mode**: Provides min-max range (e.g., 6-8/10) to account for evaluation subjectivity."
    }
    st.info(mode_descriptions[evaluation_mode])
    
    st.markdown("---")
    st.markdown("### How to use:")
    st.markdown("""
    1. Enter your Claude API key
    2. Select evaluation mode
    3. Upload your answer sheet PDF
    4. Click 'Evaluate Answer Sheet'
    5. View detailed results with marks
    """)
    
    st.markdown("---")
    st.markdown("### Features:")
    st.markdown("""
    ✓ Consistent evaluation (same file = same results)
    ✓ Three evaluation modes
    ✓ Marks shown per answer
    ✓ Summary page with missing points
    ✓ Improvement suggestions
    ✓ Downloadable results
    """)
    
    st.markdown("---")
    # Cache management
    if st.button("🗑️ Clear Evaluation Cache"):
        st.session_state['evaluation_cache'] = {}
        if 'evaluation' in st.session_state:
            del st.session_state['evaluation']
        if 'filename' in st.session_state:
            del st.session_state['filename']
        st.success("Cache cleared!")
        st.rerun()

# Main content area
col1, col2 = st.columns([1, 1])

with col1:
    st.header("📤 Upload Answer Sheet")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=['pdf'],
        help="Upload the handwritten answer sheet in PDF format"
    )
    
    custom_criteria = ""
    
    if uploaded_file is not None:
        st.success(f"✓ File uploaded: {uploaded_file.name}")
        st.info(f"File size: {len(uploaded_file.getvalue()):,} bytes")
        
        # Show selected mode
        mode_emoji = {"standard": "📗", "strict": "📕", "range": "📘"}
        st.info(f"Evaluation Mode: {mode_emoji[evaluation_mode]} {evaluation_mode.capitalize()}")
        
        # Optional: Custom evaluation criteria
        with st.expander("🎯 Custom Evaluation Criteria (Optional)"):
            custom_criteria = st.text_area(
                "Enter specific answer key or evaluation criteria:",
                placeholder="Example:\nQuestion 1: Expected answer about photosynthesis (10 marks)\nQuestion 2: Newton's law explanation (10 marks)",
                height=150
            )

with col2:
    st.header("📊 Evaluation Results")
    
    if uploaded_file is not None and api_key:
        # Generate hash for caching
        file_data = uploaded_file.getvalue()
        file_hash = get_file_hash(file_data, evaluation_mode, custom_criteria)
        
        # Check if we have cached result
        is_cached = file_hash in st.session_state['evaluation_cache']
        
        if is_cached:
            st.info("💾 Cached evaluation available for this file + settings combination")
        
        # Evaluate button
        button_text = "📋 Load Cached Evaluation" if is_cached else "🚀 Evaluate Answer Sheet"
        
        if st.button(button_text, type="primary", use_container_width=True):
            
            if is_cached:
                # Load from cache
                cached = st.session_state['evaluation_cache'][file_hash]
                st.session_state['evaluation'] = cached['evaluation']
                st.session_state['filename'] = cached['filename']
                st.session_state['mode_used'] = cached['mode_used']
                st.success("✓ Loaded cached evaluation!")
            else:
                with st.spinner("Analyzing answer sheet... This may take 30-60 seconds..."):
                    try:
                        # Initialize Claude client
                        client = anthropic.Anthropic(api_key=api_key)
                        
                        # Read and encode the PDF
                        pdf_data = base64.standard_b64encode(file_data).decode('utf-8')
                        
                        # Create evaluation prompt based on mode
                        base_prompt = get_evaluation_prompt(evaluation_mode)
                        
                        # Add custom criteria if provided
                        if custom_criteria:
                            prompt = f"{base_prompt}\n\nAdditional Evaluation Criteria Provided:\n{custom_criteria}"
                        else:
                            prompt = base_prompt
                        
                        # Send to Claude API with temperature=0 for consistency
                        message = client.messages.create(
                            model="claude-sonnet-4-20250514",
                            max_tokens=8000,
                            temperature=0,  # For consistent results
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
                        
                        # Extract evaluation
                        evaluation = message.content[0].text
                        
                        # Store in session state
                        st.session_state['evaluation'] = evaluation
                        st.session_state['filename'] = uploaded_file.name
                        st.session_state['mode_used'] = evaluation_mode
                        
                        # Cache the result
                        st.session_state['evaluation_cache'][file_hash] = {
                            'evaluation': evaluation,
                            'filename': uploaded_file.name,
                            'mode_used': evaluation_mode
                        }
                        
                        st.success("✓ Evaluation completed and cached!")
                        
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        st.info("Please check your API key and try again.")
    
    elif uploaded_file is None:
        st.info("👆 Please upload a PDF file to begin")
    elif not api_key:
        st.warning("⚠️ Please enter your API key in the sidebar")

# Display results if available
if 'evaluation' in st.session_state:
    st.markdown("---")
    st.header("📋 Detailed Evaluation Report")
    
    # Show mode used
    if 'mode_used' in st.session_state:
        mode_labels = {
            "standard": "📗 Standard Mode",
            "strict": "📕 Strict Mode", 
            "range": "📘 Range Mode"
        }
        st.info(f"Evaluated using: **{mode_labels.get(st.session_state['mode_used'], 'Standard Mode')}**")
    
    # Display the evaluation in a nice container
    st.markdown(st.session_state['evaluation'])
    
    # Download button
    st.markdown("---")
    
    mode_text = st.session_state.get('mode_used', 'standard').upper()
    result_text = f"""HANDWRITTEN ANSWER SHEET EVALUATION
{'='*70}

File: {st.session_state['filename']}
Evaluation Mode: {mode_text}

{'='*70}

{st.session_state['evaluation']}

{'='*70}
Note: This evaluation was generated using Claude AI with {mode_text} evaluation mode.
Same file uploaded with same settings will produce consistent results.
"""
    
    col_dl1, col_dl2 = st.columns(2)
    
    with col_dl1:
        st.download_button(
            label="📥 Download as TXT",
            data=result_text,
            file_name=f"evaluation_{st.session_state['filename'].replace('.pdf', '')}_{mode_text.lower()}.txt",
            mime="text/plain",
            use_container_width=True
        )
    
    with col_dl2:
        # Markdown version for better formatting
        md_result = f"""# Answer Sheet Evaluation Report

**File:** {st.session_state['filename']}  
**Evaluation Mode:** {mode_text}

---

{st.session_state['evaluation']}

---
*Generated using Claude AI - {mode_text} Evaluation Mode*
"""
        st.download_button(
            label="📥 Download as Markdown",
            data=md_result,
            file_name=f"evaluation_{st.session_state['filename'].replace('.pdf', '')}_{mode_text.lower()}.md",
            mime="text/markdown",
            use_container_width=True
        )

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    <p>Made with ❤️ using Claude API | Streamlit</p>
    <p style='font-size: 0.8em;'>💡 Tip: Same file + same mode + same criteria = Consistent results</p>
    </div>
    """,
    unsafe_allow_html=True
)
