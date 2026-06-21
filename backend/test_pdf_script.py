import asyncio
import sys
import json
from pathlib import Path

# Add the app directory to the python path so we can import modules
sys.path.append(str(Path(__file__).parent))

from app.services.pdf_parser import PDFProcessor

async def test_pdf():
    pdf_path = r"D:\Downloads\Blood_lab_report.pdf"
    
    if not Path(pdf_path).exists():
        print(json.dumps({"error": f"File not found: {pdf_path}"}))
        return

    print("Extracting text and chunking from PDF...")
    try:
        processor = PDFProcessor()
        chunks = await processor.process_pdf(pdf_path)
        
        print(f"Created {len(chunks)} chunks.")
        print("\n--- First 3 Chunks ---")
        for i, chunk in enumerate(chunks[:3]):
            print(f"\nChunk {i+1} (Page {chunk.page_number}):")
            print("-" * 40)
            print(chunk.content)
            print("-" * 40)
            
        # Write full results to a file so we can inspect it
        import dataclasses
        with open('pdf_test_results.json', 'w') as f:
            json.dump([dataclasses.asdict(c) for c in chunks], f, indent=2)
            
        print("\nFull chunking results saved to pdf_test_results.json")
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    asyncio.run(test_pdf())
