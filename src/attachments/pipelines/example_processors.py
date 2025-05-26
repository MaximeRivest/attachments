"""
Example Specialized Processors
==============================

Demonstrates specialized processors that are NOT automatically used by Attachments()
but are available through explicit access via processors.name.

Key Distinction:
- Primary processors (no name): Auto-registered for Attachments() simple API
- Named processors (with name): Only available via processors.name explicit access

Usage:
    # This will NOT use the specialized processors below
    ctx = Attachments("document.pdf")  # Uses primary processor
    
    # This WILL use the specialized processors
    result = processors.academic_pdf(attach("paper.pdf"))
    result = processors.legal_pdf(attach("contract.pdf"))
    result = processors.financial_pdf(attach("report.pdf"))
"""

from .. import load, modify, present, refine, attach
from ..core import Attachment
from . import processor

# These are NAMED processors - they will NOT be used automatically by Attachments()
# They are only available through explicit access: processors.academic_pdf()

@processor(
    match=lambda att: att.path.lower().endswith('.pdf'),
    name="academic_pdf",  # Named processor - explicit access only
    description="Specialized for academic papers with citations and references"
)
def academic_pdf_processor(att: Attachment) -> Attachment:
    """
    Specialized processor for academic papers.
    Optimized for research papers, citations, and academic structure.
    """
    
    # Academic papers benefit from structured markdown extraction
    pipeline = (load.pdf_to_pdfplumber 
               | present.markdown + present.metadata
               | refine.add_headers)
    
    return att | pipeline

@processor(
    match=lambda att: att.path.lower().endswith('.pdf'),
    name="legal_pdf",  # Named processor - explicit access only
    description="Specialized for legal documents with clause and section analysis"
)
def legal_pdf_processor(att: Attachment) -> Attachment:
    """
    Specialized processor for legal documents.
    Optimized for contracts, legal briefs, and regulatory documents.
    """
    
    # Legal documents need careful text preservation and structure
    pipeline = (load.pdf_to_pdfplumber
               | present.text + present.metadata  # Raw text for legal precision
               | refine.add_headers)
    
    return att | pipeline

@processor(
    match=lambda att: att.path.lower().endswith('.pdf'),
    name="financial_pdf",  # Named processor - explicit access only
    description="Specialized for financial reports with table and chart analysis"
)
def financial_pdf_processor(att: Attachment) -> Attachment:
    """
    Specialized processor for financial documents.
    Optimized for financial reports, statements, and data-heavy documents.
    """
    
    # Financial docs often have important tables and charts
    pipeline = (load.pdf_to_pdfplumber
               | present.markdown + present.images + present.metadata
               | refine.add_headers
               | refine.format_tables)  # Important for financial data
    
    return att | pipeline

@processor(
    match=lambda att: att.path.lower().endswith('.pdf'),
    name="medical_pdf",  # Named processor - explicit access only
    description="Specialized for medical documents with patient data handling"
)
def medical_pdf_processor(att: Attachment) -> Attachment:
    """
    Specialized processor for medical documents.
    Optimized for medical records, research papers, and clinical documents.
    """
    
    # Medical documents need careful handling and structure preservation
    pipeline = (load.pdf_to_pdfplumber
               | present.markdown + present.metadata
               | refine.add_headers)
    
    return att | pipeline

# Example of a processor for a different file type
@processor(
    match=lambda att: att.path.lower().endswith('.docx'),
    name="legal_docx",  # Named processor - explicit access only
    description="Specialized for legal Word documents"
)
def legal_docx_processor(att: Attachment) -> Attachment:
    """
    Specialized processor for legal Word documents.
    Handles track changes, comments, and legal formatting.
    """
    
    # Legal DOCX files need special handling for track changes, etc.
    pipeline = (load.docx_to_python_docx  # This would need to be implemented
               | present.text + present.metadata
               | refine.add_headers)
    
    return att | pipeline

def demo_specialized_processors():
    """Demonstrate how specialized processors work."""
    print("🎯 Specialized Processors Demo")
    print("=" * 50)
    
    # Create test attachments
    academic_att = Attachment("research_paper.pdf")
    academic_att._obj = "mock_pdf"
    academic_att.text = "Academic research paper with citations and methodology."
    
    legal_att = Attachment("contract.pdf") 
    legal_att._obj = "mock_pdf"
    legal_att.text = "Legal contract with clauses and terms."
    
    financial_att = Attachment("quarterly_report.pdf")
    financial_att._obj = "mock_pdf"
    financial_att.text = "Financial report with tables and charts."
    
    print("1. Academic PDF processor:")
    result1 = academic_pdf_processor(academic_att)
    print(f"   ✅ Processed: {type(result1)}")
    
    print("2. Legal PDF processor:")
    result2 = legal_pdf_processor(legal_att)
    print(f"   ✅ Processed: {type(result2)}")
    
    print("3. Financial PDF processor:")
    result3 = financial_pdf_processor(financial_att)
    print(f"   ✅ Processed: {type(result3)}")
    
    print("\n🔑 Key Points:")
    print("• These processors are NOT used automatically by Attachments()")
    print("• They are only available via: processors.academic_pdf()")
    print("• Multiple specialized processors can handle the same file type")
    print("• Each processor optimizes for specific domain needs")
    
    print("\n📝 Usage Examples:")
    print("```python")
    print("# Simple API uses primary processor (if exists)")
    print("ctx = Attachments('paper.pdf')  # Uses primary PDF processor")
    print("")
    print("# Explicit specialized processor access")
    print("academic = processors.academic_pdf(attach('paper.pdf'))")
    print("legal = processors.legal_pdf(attach('contract.pdf'))")
    print("financial = processors.financial_pdf(attach('report.pdf'))")
    print("")
    print("# Mix with verb system")
    print("result = processors.academic_pdf(attach('paper.pdf')) | refine.truncate")
    print("```")

if __name__ == "__main__":
    demo_specialized_processors() 