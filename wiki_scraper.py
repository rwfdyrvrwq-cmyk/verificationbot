import httpx
from bs4 import BeautifulSoup
from bs4.element import NavigableString
from typing import Optional, Dict, Any, List
import re

async def scrape_wiki_page(item_name: str) -> Optional[Dict[str, Any]]:
    """
    Scrape information from an AQW Wiki page.
    
    Args:
        item_name: The item name to look up
        
    Returns:
        dict with wiki page data or None if not found
    """
    slug = item_name.replace("'", "-")
    slug = slug.replace(' ', '-')
    slug = re.sub(r'[^a-zA-Z0-9-]', '', slug)
    slug = slug.lower()
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    
    url = f'http://aqwwiki.wikidot.com/{slug}'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, follow_redirects=True)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            page_content = soup.find('div', {'id': 'page-content'})
            if not page_content:
                return None
            
            content_text = page_content.get_text(strip=True)
            if 'does not exist' in content_text.lower() or len(content_text) < 50:
                return None
            
            title_elem = soup.find('div', {'id': 'page-title'})
            title = title_elem.get_text(strip=True) if title_elem else item_name
            
            wiki_data = {
                'title': title,
                'url': url,
                'description': None,
                'type': None,
                'level': None,
                'damage': None,
                'location': None,
                'rarity': None,
                'price': None,
                'sellback': None,
                'notes': [],
                'shop': None,
                'quest': None,
                'requirements': []
            }
            
            if 'refers to' in content_text.lower() or 'disambiguation' in content_text.lower():
                first_p = page_content.find('p')
                if first_p:
                    wiki_data['description'] = first_p.get_text(strip=True)
                
                related_links: List[Dict[str, str]] = []
                links = page_content.find_all('a')
                for link in links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    if isinstance(href, str) and href.startswith('/') and text and len(text) > 3:
                        related_links.append({
                            'name': text,
                            'url': f"http://aqwwiki.wikidot.com{href}"
                        })
                
                if related_links:
                    wiki_data['related_items'] = related_links
                
                return wiki_data
            
            parsed_fields = {}
            bold_tags = page_content.find_all(['b', 'strong'])
            
            for bold in bold_tags:
                label_text = bold.get_text(strip=True).lower().replace(':', '')
                
                value_parts = []
                current = bold.next_sibling
                
                while current:
                    if not isinstance(current, NavigableString):
                        element_name = getattr(current, 'name', None)
                        if element_name and element_name in ['b', 'strong', 'br', 'hr']:
                            break
                    
                    if isinstance(current, NavigableString):
                        text = str(current).strip()
                        if text and text not in [':', '']:
                            value_parts.append(text)
                    elif hasattr(current, 'get_text'):
                        text = current.get_text(strip=True)
                        if text and text not in [':', '']:
                            value_parts.append(text)
                    
                    current = current.next_sibling
                
                value = ' '.join(value_parts).strip()
                if value:
                    # For description, only keep the first one (don't overwrite)
                    if label_text == 'description' and 'description' in parsed_fields:
                        continue
                    parsed_fields[label_text] = value
            
            # Look for "Locations:" section
            locations_list = []
            for p in page_content.find_all('p'):
                p_text = p.get_text(strip=True)
                if p_text.startswith('Locations:'):
                    # Find all links after "Locations:"
                    next_sibling = p.find_next_sibling()
                    while next_sibling and next_sibling.name in ['p', 'ul', 'ol']:
                        if next_sibling.name in ['ul', 'ol']:
                            for li in next_sibling.find_all('li'):
                                loc_text = li.get_text(strip=True)
                                if loc_text:
                                    locations_list.append(loc_text)
                            break
                        else:
                            loc_text = next_sibling.get_text(strip=True)
                            if loc_text and not loc_text.startswith(('Price:', 'OR:', 'Reward')):
                                locations_list.append(loc_text)
                        next_sibling = next_sibling.find_next_sibling()
                    break
            
            if locations_list:
                wiki_data['locations_list'] = locations_list
            
            for label, value in parsed_fields.items():
                if 'type' in label or 'item type' in label:
                    wiki_data['type'] = value
                elif 'level' in label:
                    wiki_data['level'] = value
                elif 'damage' in label or 'base damage' in label:
                    wiki_data['damage'] = value
                elif 'location' in label:
                    wiki_data['location'] = value
                    if 'shop' in value.lower() or 'merge' in value.lower():
                        wiki_data['shop'] = value
                elif 'or' == label and 'merge' in value.lower():
                    # This is merge requirements (e.g., "OR: Merge the following...")
                    wiki_data['merge_text'] = value
                elif 'rarity' in label:
                    wiki_data['rarity'] = value
                elif 'price' in label and 'sell' not in label:
                    wiki_data['price'] = value
                    if 'quest' in value.lower() or 'reward' in value.lower():
                        wiki_data['quest'] = value
                elif 'sellback' in label:
                    wiki_data['sellback'] = value
                elif 'description' in label:
                    # Only use the FIRST description found (don't overwrite)
                    if not wiki_data['description']:
                        wiki_data['description'] = value
                elif 'require' in label or 'needed' in label:
                    if value and value not in wiki_data['requirements']:
                        wiki_data['requirements'].append(f"{label.title()}: {value}")
            
            if not wiki_data['description']:
                paragraphs = page_content.find_all('p')
                for p in paragraphs[:5]:
                    text = p.get_text(strip=True)
                    if len(text) > 30 and not text.lower().startswith(('this', 'see also', 'note')):
                        wiki_data['description'] = text
                        break
            
            notes_section = None
            for h2 in page_content.find_all(['h2', 'h3']):
                h2_text = h2.get_text(strip=True).lower()
                if 'note' in h2_text:
                    notes_section = h2
                    break
            
            if notes_section:
                next_elem = notes_section.find_next_sibling()
                while next_elem and next_elem.name not in ['h1', 'h2', 'h3']:
                    if next_elem.name == 'ul':
                        for li in next_elem.find_all('li'):
                            note_text = li.get_text(strip=True)
                            if note_text and len(note_text) > 5:
                                wiki_data['notes'].append(note_text)
                    elif next_elem.name == 'p':
                        note_text = next_elem.get_text(strip=True)
                        if note_text and len(note_text) > 5:
                            wiki_data['notes'].append(note_text)
                    next_elem = next_elem.find_next_sibling()
            
            return wiki_data
            
    except Exception as e:
        print(f'Error scraping wiki page: {e}')
        return None
