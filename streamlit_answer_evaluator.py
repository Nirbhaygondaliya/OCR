"""
Handwritten Answer Sheet Evaluator - Streamlit App
Powered by Claude API
"""

import streamlit as st
import anthropic
import base64
from io import BytesIO

# Page configuration
st.set_page_config(
    page_title="Answer Sheet Evaluator",
    page_icon="📝",
    layout="wide"
)

# Title and description
st.title("📝 Handwritten Answer Sheet Evaluator")
st.markdown("### Powered by Claude AI")
st.markdown("---")

# Sidebar for API key
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Get API key from secrets (secure)
    try:
        api_key = st.secrets["ANTHROPIC_API_KEY"]
        st.success("✓ API Key loaded from secrets")
    except:
        api_key = st.text_input(
            "Enter your Anthropic API Key:",
            type="password",
            help="Your API key will not be stored"
        )
    
    st.markdown("---")
    st.markdown("### How to use:")
    st.markdown("""
    1. Enter your Claude API key
    2. Upload your answer sheet PDF
    3. Click 'Evaluate Answer Sheet'
    4. View detailed results with marks
    """)
    
    st.markdown("---")
    st.markdown("### Features:")
    st.markdown("""
    ✓ Automatic answer detection
    ✓ Individual question scoring
    ✓ Detailed feedback
    ✓ Total marks calculation
    ✓ Downloadable results
    """)

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
    
    if uploaded_file is not None:
        st.success(f"✓ File uploaded: {uploaded_file.name}")
        st.info(f"File size: {len(uploaded_file.getvalue()):,} bytes")
        
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
        # Evaluate button
        if st.button("🚀 Evaluate Answer Sheet", type="primary", use_container_width=True):
            
            with st.spinner("Analyzing answer sheet... This may take 10-30 seconds..."):
                try:
                    # Initialize Claude client
                    client = anthropic.Anthropic(api_key=api_key)
                    
                    # Read and encode the PDF
                    file_data = uploaded_file.getvalue()
                    pdf_data = base64.standard_b64encode(file_data).decode('utf-8')
                    
                    # Create evaluation prompt
                    base_prompt = """Please carefully evaluate this handwritten answer sheet PDF.

For each question/answer you find:
1. Identify the question number
2. Read and transcribe what the student wrote
3. Evaluate the answer for correctness and completeness
4. Assign marks/score for each answer
5. Provide specific feedback (what's correct, what's missing, any errors)

Then provide:
- Question-by-question breakdown with marks
- Detailed feedback for each answer
- Assessment of handwriting legibility (if applicable)
- Total marks scored
- Overall percentage
- Suggestions for improvement

Please format your response clearly with headers for each question."""

                    # Add custom criteria if provided
                    if custom_criteria:
                        prompt = f"{base_prompt}\n\nEvaluation Criteria:\n{custom_criteria}"
                    else:
                        prompt = base_prompt
                    
                    # Send to Claude API
                    message = client.messages.create(
                        model="model="claude-haiku-4-5-20251001",",
                        max_tokens=4000,
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
                    
                    st.success("✓ Evaluation completed!")
                    
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
    
    # Display the evaluation
    st.markdown(st.session_state['evaluation'])
    
    # Download button
    st.markdown("---")
    result_text = f"""HANDWRITTEN ANSWER SHEET EVALUATION
{'='*70}

File: {st.session_state['filename']}

{'='*70}

{st.session_state['evaluation']}
"""
    
    st.download_button(
        label="📥 Download Evaluation Report",
        data=result_text,
        file_name=f"evaluation_{st.session_state['filename'].replace('.pdf', '')}.txt",
        mime="text/plain",
        use_container_width=True
    )

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: gray;'>
    Made with ❤️ using Claude API | Streamlit
    </div>
    """,
    unsafe_allow_html=True
)
