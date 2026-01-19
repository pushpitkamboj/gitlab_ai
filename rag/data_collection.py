import json
from typing import List
from dotenv import load_dotenv
load_dotenv()

from pydantic import BaseModel
from langchain.chat_models import init_chat_model
llm = init_chat_model("gpt-4o", model_provider="openai")

class output_format(BaseModel):
    links: List[str]

prompt = '''
You are an expert in gitlab and scouting and eliminating information from given json data.
You have been given content about the links, title and description about gitlab. Your task is to filter the urls based on title and description.
Filter them based on if they are relevant or not, for eg
  {
    "url": "https://handbook.gitlab.com/handbook/engineering/careers/matrix/senior",
    "title": "Engineering Career Framework: Senior | The GitLab Handbook",
    "description": "Engineering Function Competencies: Senior Seniors at GitLab are expected to exhibit the following competencies:\nSenior Leadership Competencies Senior Technic..."
  }
  this information is not valid for us because it involves careers page links.The relevant information are :
    {
    "url": "https://handbook.gitlab.com/handbook/engineering/architecture/design-documents",
    "title": "Architecture Design Documents | The GitLab Handbook",
    "description": "Design documents are the primary artifact that the architecture design workflow revolves around. A design document describes a technical vision and a set of ..."
  }
  this involves information about gitlab which is important for us, so keep this.
  
  REMEMBER:
  our aim is to take the gitlab specific informations and eliminate non related to gitlab tooling which is not relevant for developers/customers who will be using gitlab.

'''

def filter_links(input_file: str = "gitlab_sitemap.json", output_file: str = "filtered_links.json", batch_size: int = 100):
    """
    Load JSON, filter with LLM, save filtered results.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        all_links = json.load(f)
    
    print(f"Loaded {len(all_links)} links from {input_file}")
    
    structured_llm = llm.with_structured_output(output_format)
    filtered_urls = []
    
    for i in range(0, len(all_links), batch_size):
        batch = all_links[i:i + batch_size]
        batch_json = json.dumps(batch, indent=2)
        
        print(f"Processing batch {i // batch_size + 1} ({len(batch)} links)...")
        
        response = structured_llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Filter these links:\n{batch_json}"}
        ])
        
        filtered_urls.extend(response.links)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered_urls, f, indent=2, ensure_ascii=False)
    
    print(f"\nFiltered: {len(all_links)} → {len(filtered_urls)} links")
    print(f"Saved to: {output_file}")
    
    return filtered_urls

def total_filtered_links(input_file="gitlab_sitemap.json"):
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
        print(len(data))

if __name__ == "__main__":
    filter_links()
    total_filtered_links()