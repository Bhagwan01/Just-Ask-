import asyncio
import sys
import os

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.pdf_parser import PDFProcessor

async def test_pdf(file_path):
    print(f"Testing PDF: {file_path}")
    parser = PDFProcessor()
    try:
        chunks = await parser.process_pdf(file_path)
        print(f"Success! Extracted {len(chunks)} chunks.")
        for i, chunk in enumerate(chunks):
            print(f"\n--- Chunk {i} ---")
            print(chunk.content)
    except Exception as e:
        print(f"Error processing PDF: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_pdf("/app/test_report.pdf"))
