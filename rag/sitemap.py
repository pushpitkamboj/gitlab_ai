import json
from firecrawl import Firecrawl
from dotenv import load_dotenv
load_dotenv()

firecrawl = Firecrawl()

urls = ["https://handbook.gitlab.com/", "https://about.gitlab.com/direction/"]

def create_sitemap(urls, limit = 1000):
    """
    Create sitemap for given URLs and save to JSON.
    """
    all_links = []
    
    for url in urls:
        print(f"Mapping: {url}")
        res = firecrawl.map(url=url, limit=limit)
        
        if res and hasattr(res, 'links'):
            for link in res.links:
                link_data = {
                    "url": link.url,
                    "title": link.title,
                    "description": link.description
                }
                all_links.append(link_data)
            print(f"  Found {len(res.links)} links")
    
    output_file = "gitlab_sitemap.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_links, f, indent=2, ensure_ascii=False)
    
    print(f"\nTotal links saved: {len(all_links)}")
    print(f"Saved to: {output_file}")
    
    return all_links

if __name__ == "__main__":
    create_sitemap(urls)

# Mapping: https://handbook.gitlab.com/
#   Found 769 links
# Mapping: https://about.gitlab.com/direction/
#   Found 152 links

# Total links saved: 921
# Saved to: gitlab_sitemap.json
