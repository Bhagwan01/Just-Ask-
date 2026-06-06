from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List,Dict,Optional
import logging
import os
from pathlib import Path
from dataclasses import dataclass
from backend.app.config import Config

#configure logging
logger=logging.getLogger(__name__)

@dataclass
class PDFConfig:
    chunk_size: int = None
    chunk_overlap: int = None
    min_chunk_length: int = None
    separators: List[str] = None
    
    def __post_init__(self):
        # Use Config values from .env, or defaults if not set
        if self.chunk_size is None:
            self.chunk_size = Config.PDF_CHUNK_SIZE
        
        if self.chunk_overlap is None:
            self.chunk_overlap = Config.PDF_CHUNK_OVERLAP
        
        if self.min_chunk_length is None:
            self.min_chunk_length = Config.PDF_MIN_CHUNK_LENGTH
        
        if self.separators is None:
            self.separators = ["\n\n", "\n", ". ", " ", ""]
        
        # Validate configuration
        if self.chunk_size < 100:
            raise ValueError("chunk_size must be >= 100")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
class PDFExtractionError(Exception):
    pass

class PDFProcessor:

    def __init__(self,config:Optional[PDFConfig]=None):
        self.config=config or PDFConfig
        self._validate_config()
        logger.info(f"PDFProcessor initialized with chunk_size={self.config.chunk_size}")

    def _validate_config(self) -> None:
        if self.config.chunk_size<100:
            raise ValueError("Chunk size must be greater than 100 ")
        if self.config.chunk_overlap>=self.config.chunk_size :
            raise ValueError("chunk_overlap must be less than chunk size")
        if self.config.min_chunk_length<10:
            raise ValueError("min chunk length must be greater than 10")
    
    def extract_text_from_pdf(self,pdf_path:str) -> Dict:
        try:
            #validate pdf
            pdf_file_path=Path(pdf_path)
            if not pdf_file_path.exists():
                raise FileNotFoundError(f"file not found : {pdf_path}")
            if not pdf_file_path.is_file():
                raise PDFExtractionError(f"pdf path is not a file :{pdf_path}")
            
         
            # load the pdf
            loader=PyPDFLoader(pdf_path)
            docs=loader.load()

            if not docs:
                raise PDFExtractionError(f"no content extracted from pdf path:{pdf_path}")
            
            logger.info(f"Successfully loaded PDF with {len(docs)} pages")
            

            full_text=""
            page_data=[] 
            for doc in docs:
                page_num=doc.metadata["page"]+1
                page_text=doc.page_data

                #skip empty pages

                if not page_text.strip():
                    logger.warning(f"page{page_num} is empty")
                    continue

                page_data.append({
                    "page_number":page_num,
                    "start_char":len(full_text),
                    "text_length":len(page_text)
                }
                )
                full_text+=page_text+ "\n\n"

            if not full_text.strip():
                raise PDFExtractionError("No text content found in pdf")
            
            logger.info(f"Extracted {len(full_text)} characters from {len(page_data)} pages")
                
            return {
                "text":full_text,
                "page_data":page_data,
                "total_pages":len(docs),
                "document":docs
            }
        except FileNotFoundError:
            logger.warning(f"pdf file not found : {pdf_path}")
            raise
        except Exception as e:
            logger.error(f"Error extracting pdf:{str(e)}")
            raise PDFExtractionError(f"failed to extract pdf :{str(e)}") from e
        

    def chunk_from_text(self,extracted_doc:Dict) -> List[Dict]:
        try:
            #validate inputs
            required_keys=['text','page_data']
            if not all(key in extracted_doc for key in required_keys):
                raise ValueError(f"extracted doc is missing required keys:{required_keys}")
            
            text=extracted_doc["text"]
            page_data=extracted_doc["page_data"]

            if not text.strip():
                raise ValueError("Text is empty")
            
            logger.info(f"Starting chunking: {len(text)} characters, chunk_size={self.config.chunk_size}")

            #load the textsplitter
            loader=RecursiveCharacterTextSplitter(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                separators=self.config.separators
            )

            chunk_strings=loader.split_text(text)
            logger.info(f"Created {len(chunk_strings)} chunks")

            if not chunk_strings:
                raise PDFExtractionError("text splitter does not contain any chunks")

            chunks=[]

            for chunk_content in chunk_strings:
                #skip small chunk
                if len(chunk_content.strip())<self.config.min_chunk_length:
                    logger.debug(f"skipped smaller chunk :{len(chunk_content)} chars")
                    continue
                #find which page this chunk belong
                page_num=self._find_chunk_page(chunk_content,text,page_data)
                
                chunks.append({
                    "content":chunk_content,
                    "page_number":page_num,
                    "word_count":len(chunk_content.split()),
                    "char_count": len(chunk_content)
                })

            logger.info(f"Created {len(chunks)} valid chunks after filtering")

            # Log chunk statistics
            avg_chunk_size = sum(c["char_count"] for c in chunks) / len(chunks) if chunks else 0
            logger.info(f"Chunk statistics - Avg size: {avg_chunk_size:.0f} chars, "
                       f"Min: {min(c['char_count'] for c in chunks)}, "
                       f"Max: {max(c['char_count'] for c in chunks)}")
            
            return chunks
        except ValueError as e:
            logger.error(f"vaidation error during chunking :{str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error during chunking texts:{str(e)}")
            raise PDFExtractionError(f"faild to extract chunks:{str(e)}")
        
    def _find_chunk_page(self,chunk:str,full_text:str,page_data:List[Dict]) -> int:
        try:
            chunk_pos=full_text.find(chunk)

            if(chunk_pos==-1):
                search_str=chunk[:100]
                chunk_pos=full_text.find(search_str)
            
            if(chunk_pos==-1):
                logger.warning("chunk poistion not fount ,defaulting to page 1")
                return 1
            
            for page_info in page_data:
                page_start=page_info['start_char']
                page_end=page_start+page_info['text_length']

                if chunk_pos>= page_start and chunk_pos<page_end:
                    return page_info['page_number']
                
            #if page not found return last page
            return page_data[-1]['page_number'] if page_data else 1
            
        except Exception as e:
            logger.error(f"error finding chunk page:{str(e)}")
            return 1
        
    def process_pdf(self,pdf_path:str) -> List[Dict]:

        logger.info(f"Starting full PDF processing pipeline: {pdf_path}")

         #extract text
        extracted=self.extract_text_from_pdf(pdf_path)

        #extract chunks
        chunks=self.chunk_from_text(extracted)

        logger.info(f"Pipeline complete: {len(chunks)} chunks ready for embedding")

        return chunks


        
    











    







