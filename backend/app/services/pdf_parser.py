from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List,Dict

def extract_text_from_pdf(pdf_path) -> Dict:

    # load the pdf
    loader=PyPDFLoader(pdf_path)
    docs=loader.load()

    full_text=""
    pageContent=[] 
    for doc in docs:
        page_num=doc.metadata["page"]+1
        page_text=doc.page_content

        pageContent.append({
            "page_Number":page_num,
            "start_char":len(full_text),
            "text_length":len(page_text)
        }
        )
        full_text+=page_text

    return {
        "text":full_text,
        "page_data":pageContent,
        "total_pages":len(docs),
        "document":docs
    }

def chunk_from_text(extracted_doc:Dict,chunk_size:int=1000,chunk_overlap:int=200) -> List[Dict]:
    text=extracted_doc["text"]
    page_content=extracted_doc["page_data"]

    #load the textsplitter
    loader=RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""] 
    )

    chunks_data=loader.split_text(text)

    chunks=[]
    curr=0

    for chunk in chunks_data:
        page_num=1

        for pageInfo in page_content:

            page_start=pageInfo["start_char"]
            page_end=page_start+pageInfo["text_length"]

            if curr>=page_start and curr<page_end:
                page_num=pageInfo["page_Number"]
                break
        
        chunks.append({
            "content":chunk,
            "page_number":page_num,
            "start_idx":curr,
            "word_count":len(chunk.split()),
            "char_count": len(chunk)
        })

        curr+=len(chunk)-chunk_overlap
    
    return chunks










    







