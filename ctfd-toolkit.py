#!/usr/bin/env python3
"""
CTFd Toolkit - Complete CTF Management Tool

A comprehensive toolkit for CTFd platforms with session caching, 
browser-like headers, and beautiful UI.
"""

import argparse
import requests
import json
import re
import sys
import os
import getpass
import hashlib
import shutil
import fcntl
import termios
import struct
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timedelta
import time
import signal

# Configuration
DEFAULT_TARGET = "https://ctf.example.com"
CACHE_DIR = Path.home() / ".cache" / "ctfd_toolkit"
CACHE_FILE = CACHE_DIR / "session.json"
CACHE_DURATION = timedelta(hours=24)  # Cache valid for 24 hours

# Global terminal width cache
_terminal_width = None

def _handle_sigwinch(signum, frame):
    """Signal handler for terminal resize"""
    global _terminal_width
    _terminal_width = None  # Invalidate cache

# Register SIGWINCH handler if possible
try:
    signal.signal(signal.SIGWINCH, _handle_sigwinch)
except (ValueError, OSError):
    pass  # SIGWINCH not available on this platform


def get_terminal_width():
    """
    Get terminal width using multiple methods (like btop/htop)
    Priority: ioctl > COLUMNS env > shutil > stty > default
    """
    global _terminal_width
    
    # Return cached value if available
    if _terminal_width is not None:
        return _terminal_width
    
    width = None
    
    # Method 1: ioctl TIOCGWINSZ (most reliable, used by btop/htop)
    try:
        # Try stdin first, then stdout, then stderr
        for fd in [sys.stdin.fileno(), sys.stdout.fileno(), sys.stderr.fileno()]:
            try:
                result = fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack('HHHH', 0, 0, 0, 0))
                rows, cols, xpixel, ypixel = struct.unpack('HHHH', result)
                if cols > 0:
                    width = cols
                    break
            except (OSError, IOError):
                continue
    except Exception:
        pass
    
    # Method 2: COLUMNS environment variable
    if width is None:
        try:
            cols = os.environ.get('COLUMNS')
            if cols:
                width = int(cols)
        except Exception:
            pass
    
    # Method 3: shutil.get_terminal_size() (uses stty internally)
    if width is None:
        try:
            size = shutil.get_terminal_size()
            if size.columns > 0:
                width = size.columns
        except Exception:
            pass
    
    # Method 4: stty size command
    if width is None:
        try:
            import subprocess
            result = subprocess.run(['stty', 'size'], capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                rows, cols = map(int, result.stdout.split())
                if cols > 0:
                    width = cols
        except Exception:
            pass
    
    # Default to 120 for modern terminals
    if width is None or width < 40:
        width = 120
    
    # Cache the result
    _terminal_width = width
    return width


def reset_terminal_width():
    """Reset cached terminal width (called on SIGWINCH)"""
    global _terminal_width
    _terminal_width = None


# Browser-like headers
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}

API_HEADERS = {
    'User-Agent': BROWSER_HEADERS['User-Agent'],
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'X-Requested-With': 'XMLHttpRequest',
    'Content-Type': 'application/json',
}


class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'
    
    # Box drawing characters
    BOX_TOP_LEFT = '┌'
    BOX_TOP_RIGHT = '┐'
    BOX_BOTTOM_LEFT = '└'
    BOX_BOTTOM_RIGHT = '┘'
    BOX_HORIZONTAL = '─'
    BOX_VERTICAL = '│'
    BOX_T_DOWN = '┬'
    BOX_T_UP = '┴'
    BOX_T_RIGHT = '├'
    BOX_T_LEFT = '┤'
    BOX_CROSS = '┼'


class SessionCache:
    """Manage session cookie caching"""
    
    def __init__(self, target, username):
        self.target = target
        self.username = username
        self.cache_key = hashlib.md5(f"{target}:{username}".encode()).hexdigest()[:8]
        self.cache_file = CACHE_DIR / f"session_{self.cache_key}.json"
        
    def load(self):
        """Load cached session if valid"""
        try:
            if not self.cache_file.exists():
                return None
            
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            # Check if cache is still valid
            cached_time = datetime.fromisoformat(data['timestamp'])
            if datetime.now() - cached_time > CACHE_DURATION:
                os.remove(self.cache_file)
                return None
            
            return data.get('cookies', {})
        except Exception:
            return None
    
    def save(self, cookies):
        """Save session cookies to cache"""
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            
            data = {
                'timestamp': datetime.now().isoformat(),
                'target': self.target,
                'username': self.username,
                'cookies': cookies
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(data, f)
            
            # Set file permissions (readable only by owner)
            os.chmod(self.cache_file, 0o600)
            
        except Exception as e:
            print(f"{Colors.DIM}[!] Cache save error: {e}{Colors.RESET}")
    
    def clear(self):
        """Clear cached session"""
        try:
            if self.cache_file.exists():
                os.remove(self.cache_file)
        except Exception:
            pass


class CTFdManager:
    def __init__(self, target, username, password, verbose=False, no_cache=False):
        self.target = target.rstrip('/')
        self.username = username
        self.password = password
        self.verbose = verbose
        self.no_cache = no_cache
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)
        self.challenges = []
        self.categories = {}
        self.cache = SessionCache(target, username)
        
    def login(self):
        """Login to CTFd with session caching"""
        # Try to load cached session
        if not self.no_cache:
            cached_cookies = self.cache.load()
            if cached_cookies:
                self.session.cookies.update(cached_cookies)
                
                # Test if session is still valid
                try:
                    r = self.session.get(self.target + "/api/v1/challenges", timeout=10)
                    if r.status_code == 200:
                        if self.verbose:
                            print(f"{Colors.GREEN}[+] Using cached session{Colors.RESET}")
                        return True
                except Exception:
                    pass
                
                if self.verbose:
                    print(f"{Colors.DIM}[i] Cached session expired, re-login...{Colors.RESET}")
        
        # Perform login
        try:
            r = self.session.get(self.target + '/login', timeout=10)
            matched = re.search(b"""('csrfNonce':[ \t]+"([a-f0-9A-F]+))""", r.content)
            nonce = matched.groups()[1] if matched else b''
            
            r = self.session.post(
                self.target + '/login',
                data={
                    'name': self.username,
                    'password': self.password,
                    '_submit': 'Submit',
                    'nonce': nonce.decode('UTF-8')
                },
                timeout=10
            )
            
            success = 'Your username or password is incorrect' not in r.text
            
            if success:
                # Visit challenges page to establish proper session
                self.session.headers.update(API_HEADERS)
                self.session.get(self.target + '/challenges', timeout=10)
                self.session.get(self.target + '/api/v1/challenges', timeout=10)
                
                # Cache the session
                if not self.no_cache:
                    self.cache.save(dict(self.session.cookies))
                
                if self.verbose:
                    print(f"{Colors.GREEN}[+] Login successful{Colors.RESET}")
            
            return success
        except Exception as e:
            if self.verbose:
                print(f"{Colors.RED}[!] Login error: {e}{Colors.RESET}")
            return False
    
    def fetch_challenges(self):
        """Fetch all challenges from CTFd"""
        try:
            r = self.session.get(self.target + "/api/v1/challenges", timeout=10)
            if r.status_code == 200:
                self.challenges = json.loads(r.content)['data']
                
                # Group by category
                self.categories = defaultdict(list)
                for c in self.challenges:
                    cat = c.get('category', 'Unknown')
                    self.categories[cat].append(c)
                
                # Sort each category by solves
                for cat in self.categories:
                    self.categories[cat].sort(key=lambda x: -x['solves'])
                
                return True
        except Exception as e:
            if self.verbose:
                print(f"{Colors.RED}[!] Error fetching challenges: {e}{Colors.RESET}")
        return False
    
    def get_solved_count(self):
        """Get count of solved challenges"""
        return sum(1 for c in self.challenges if c.get('solved_by_me'))
    
    def get_total_count(self):
        """Get total challenge count"""
        return len(self.challenges)
    
    def show_status(self, auto_save=True):
        """Show overall challenge status - Clean compact layout"""
        solved = self.get_solved_count()
        total = self.get_total_count()
        percentage = 100 * solved / total if total > 0 else 0
        
        print()
        
        # Header - fixed width for consistent look
        box_width = 68
        title = "CTF STATUS OVERVIEW"
        padding = (box_width - len(title)) // 2
        
        print(f"{Colors.BOLD}{Colors.CYAN}╔{'═' * box_width}╗{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}{' ' * padding}{Colors.BOLD}{title}{Colors.RESET}{' ' * (box_width - padding - len(title))}{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}╚{'═' * box_width}╝{Colors.RESET}")
        print()
        
        # Category breakdown with challenges
        print(f"  {Colors.BOLD}{Colors.BLUE}CATEGORY BREAKDOWN{Colors.RESET}")
        print()
        
        # Find max challenge name length for proper column width
        max_name_len = 0
        for cat_challs in self.categories.values():
            for c in cat_challs:
                max_name_len = max(max_name_len, len(c['name']))
        
        # Fixed column widths for consistent alignment
        cat_width = max(30, min(max_name_len, 52))  # Max 52 to fit within 68 char width
        stats_width = 6  # Width for "X/Y" stats
        pct_width = 7    # Width for "(XXX.X%)" - fixed for alignment
        solves_width = 15  # Width for "XXX solves"
        
        for cat in sorted(self.categories.keys()):
            cat_challs = self.categories[cat]
            cat_solved = sum(1 for c in cat_challs if c.get('solved_by_me'))
            cat_total = len(cat_challs)
            cat_pct = 100 * cat_solved / cat_total if cat_total > 0 else 0
            
            # Color: Green if all solved, Yellow if any unsolved
            if cat_solved == cat_total:
                cat_color = Colors.GREEN
            else:
                cat_color = Colors.YELLOW
            
            # Category header with stats - aligned with challenge solve counts
            stats = f"{cat_solved:>2}/{cat_total}"
            pct = f"({cat_pct:5.1f}%)"  # Fixed width 7: (XX.X%) or (XXX.X%)
            # Right-align stats and percentage together to align with "XXX solves"
            stats_pct = f"{stats:>6}  {pct:>7}"
            print(f"  {cat_color}┌─ {Colors.BOLD}{cat:<{cat_width}}{Colors.RESET}  {stats_pct}")
            
            # Challenges in category - sorted by solves (most solved first)
            for c in sorted(cat_challs, key=lambda x: -x['solves']):
                status_color = Colors.GREEN if c.get('solved_by_me') else Colors.YELLOW
                status_icon = "●" if c.get('solved_by_me') else "○"
                solves_str = f"{c['solves']} solves"
                print(f"  {cat_color}│{Colors.RESET}  {status_color}{status_icon} {c['name']:<{cat_width}} {status_color}{solves_str:>{solves_width}}{Colors.RESET}")
            
            print(f"  {cat_color}└{Colors.RESET}")
            
            # Only add blank line between categories, not after the last one
            if cat != sorted(self.categories.keys())[-1]:
                print()
        
        print()
        
        # Summary stats at the end
        print(f"  {Colors.BOLD}Total:{Colors.RESET} {total:>4}  │  {Colors.GREEN}Solved:{Colors.RESET} {solved:>4}  │  {Colors.YELLOW}Unsolved:{Colors.RESET} {total - solved:>4}  │  {Colors.YELLOW}Progress:{Colors.RESET} {percentage:>5.1f}%")
        print(f"  {Colors.DIM}{'─' * 68}{Colors.RESET}")
        bar_width = 56
        filled = int(bar_width * solved / total)
        bar = f"{Colors.GREEN}{'█' * filled}{Colors.DIM}{'░' * (bar_width - filled)}{Colors.RESET}"
        print(f"  [{bar}] {solved}/{total}")
        print()
        
        # Auto-save status to JSON (silent, no message)
        if auto_save:
            self.save_status_json("ctfd_status.json")
    
    def save_status_json(self, output_file="ctfd_status.json"):
        """Save challenge status to JSON file"""
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'target': self.target,
                'username': self.username,
                'summary': {
                    'total': self.get_total_count(),
                    'solved': self.get_solved_count(),
                    'unsolved': self.get_total_count() - self.get_solved_count(),
                    'progress_pct': round(100 * self.get_solved_count() / self.get_total_count(), 2) if self.get_total_count() > 0 else 0
                },
                'categories': {},
                'challenges': []
            }
            
            # Group by category
            for cat in sorted(self.categories.keys()):
                cat_challs = self.categories[cat]
                cat_solved = sum(1 for c in cat_challs if c.get('solved_by_me'))
                data['categories'][cat] = {
                    'total': len(cat_challs),
                    'solved': cat_solved,
                    'progress_pct': round(100 * cat_solved / len(cat_challs), 2) if len(cat_challs) > 0 else 0
                }
            
            # Add all challenges
            for c in sorted(self.challenges, key=lambda x: (-x['solves'], x['name'])):
                data['challenges'].append({
                    'id': c['id'],
                    'name': c['name'],
                    'category': c.get('category', 'Unknown'),
                    'solves': c['solves'],
                    'value': c.get('value', c.get('points', 0)),
                    'solved_by_me': c.get('solved_by_me', False)
                })
            
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            return output_file
        except Exception as e:
            if self.verbose:
                print(f"{Colors.DIM}[!] Error saving JSON: {e}{Colors.RESET}")
            return None
    
    def list_challenges(self, solved_only=False, unsolved_only=False, category_filter=None):
        """List challenges - matching status dashboard design"""
        if solved_only:
            title = "SOLVED CHALLENGES"
            challenges = [c for c in self.challenges if c.get('solved_by_me')]
        elif unsolved_only:
            title = "UNSOLVED CHALLENGES"
            challenges = [c for c in self.challenges if not c.get('solved_by_me')]
        else:
            title = "ALL CHALLENGES"
            challenges = self.challenges

        if category_filter:
            challenges = [c for c in challenges if category_filter.lower() in c.get('category', '').lower()]
            title = f"{title} ({category_filter})"

        # Sort by solves
        challenges.sort(key=lambda x: -x['solves'])

        print()

        # Find max challenge name length for proper column width
        max_name_len = max(len(c['name']) for c in challenges) if challenges else 0

        # Fixed column widths for consistent alignment (matching status dashboard)
        cat_width = max(30, min(max_name_len, 52))
        solves_width = 15

        # Group by category
        by_category = defaultdict(list)
        for c in challenges:
            by_category[c.get('category', 'Unknown')].append(c)

        for cat in sorted(by_category.keys()):
            cat_challs = by_category[cat]
            cat_solved = sum(1 for c in cat_challs if c.get('solved_by_me'))
            cat_total = len(cat_challs)
            cat_pct = 100 * cat_solved / cat_total if cat_total > 0 else 0

            # Color: Green if all solved, Yellow if any unsolved
            if cat_solved == cat_total:
                cat_color = Colors.GREEN
            else:
                cat_color = Colors.YELLOW

            # Category header with stats (matching status dashboard)
            stats = f"{cat_solved:>2}/{cat_total}"
            pct = f"({cat_pct:5.1f}%)"
            stats_pct = f"{stats:>6}  {pct:>7}"
            print(f"  {cat_color}┌─ {Colors.BOLD}{cat:<{cat_width}}{Colors.RESET}  {stats_pct}")

            # Challenges in category (matching status dashboard)
            for c in sorted(cat_challs, key=lambda x: -x['solves']):
                status_color = Colors.GREEN if c.get('solved_by_me') else Colors.YELLOW
                status_icon = "●" if c.get('solved_by_me') else "○"
                solves_str = f"{c['solves']} solves"
                print(f"  {cat_color}│{Colors.RESET}  {status_color}{status_icon} {c['name']:<{cat_width}} {status_color}{solves_str:>{solves_width}}{Colors.RESET}")

            print(f"  {cat_color}└{Colors.RESET}")

            # Only add blank line between categories
            if cat != sorted(by_category.keys())[-1]:
                print()

        print()

    def find_challenge(self, name):
        """Find challenge by name (partial match)"""
        name_lower = name.lower()
        for c in self.challenges:
            if name_lower in c['name'].lower():
                return c
        return None
    
    def download_files(self, category_filter=None, output_dir="./"):
        """Download challenge files - Reference: ctfd_parser.py"""
        
        # Get all categories dynamically from fetched challenges
        categories = sorted(list(set(c.get('category', 'Unknown') for c in self.challenges)))
        
        # Filter categories if category_filter is specified
        if category_filter:
            categories = [c for c in categories if category_filter.lower() in c.lower()]
        
        if not categories:
            print(f"  {Colors.DIM}No categories to download.{Colors.RESET}\n")
            return

        total_downloaded = 0
        total_size = 0
        total_skipped = 0
        
        print()
        print(f"{Colors.BOLD}Downloading challenge files...{Colors.RESET}")
        print()

        # Process each category
        for category in categories:
            cat_challs = [c for c in self.challenges if c.get('category') == category]

            # Determine category color (green if all solved, yellow if any unsolved)
            cat_solved = sum(1 for c in cat_challs if c.get('solved_by_me'))
            cat_total = len(cat_challs)
            if cat_solved == cat_total:
                cat_color = Colors.GREEN
            else:
                cat_color = Colors.YELLOW

            # Sanitize category name for directory (replace spaces with underscores)
            safe_cat = category.replace(' ', '_')

            # Category header (colored, matching status dashboard)
            print(f"  {cat_color}┌─ {Colors.BOLD}{category}{Colors.RESET}")
            
            # Process each challenge in category
            for challenge in cat_challs:
                name = challenge['name']
                chall_id = challenge['id']

                # Sanitize challenge name for directory (replace spaces with underscores)
                safe_name = name.replace(' ', '_')
                challenge_dir = Path(output_dir) / safe_cat / safe_name
                challenge_dir.mkdir(parents=True, exist_ok=True)

                # Challenge name display (green if solved, yellow if not - matching status dashboard)
                name_display = name.replace(' ', '_')
                status_color = Colors.GREEN if challenge.get('solved_by_me') else Colors.YELLOW
                status_icon = "●" if challenge.get('solved_by_me') else "○"
                print(f"  {cat_color}│{Colors.RESET}  {status_color}{status_icon} {name_display}{Colors.RESET}")

                # Get challenge details from API
                try:
                    r = self.session.get(f"{self.target}/api/v1/challenges/{chall_id}", timeout=10)
                    if r.status_code != 200:
                        print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}(error fetching details){Colors.RESET}")
                        continue

                    chall_data = json.loads(r.content)['data']
                    files = chall_data.get('files', [])

                    # Download files if any
                    if files:
                        for file_url in files:
                            # Extract filename
                            if '?' in file_url:
                                filename = file_url.split('?')[0].split('/')[-1]
                            else:
                                filename = file_url.split('/')[-1]

                            file_path = challenge_dir / filename

                            # Check file size first
                            try:
                                head_r = self.session.head(f"{self.target}{file_url}", timeout=10)
                                file_size = int(head_r.headers.get('Content-Length', 0))

                                if file_size > 100 * 1024 * 1024:  # 100 MB limit
                                    print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}⚠ {filename} (too large){Colors.RESET}")
                                    continue
                            except Exception:
                                pass

                            # Download file
                            try:
                                # Check if already exists
                                if file_path.exists():
                                    existing_size = file_path.stat().st_size

                                    # Compare sizes to detect changes
                                    if existing_size == file_size:
                                        # Same size, likely the same file - skip
                                        print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}⊘ {filename} ({self._format_size(existing_size)}){Colors.RESET}")
                                        total_skipped += 1
                                        total_downloaded += 1
                                        total_size += existing_size
                                    else:
                                        # Different size, file changed - re-download
                                        print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}⟳ {filename} ({self._format_size(existing_size)} → {self._format_size(file_size)}){Colors.RESET}")

                                        r = self.session.get(f"{self.target}{file_url}", stream=True, timeout=30)
                                        downloaded = 0

                                        with open(file_path, 'wb') as f:
                                            for chunk in r.iter_content(chunk_size=8192):
                                                f.write(chunk)
                                                downloaded += len(chunk)

                                        size_str = self._format_size(downloaded)
                                        print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}✓ {filename} ({size_str}){Colors.RESET}")
                                        total_downloaded += 1
                                        total_size += downloaded
                                    continue

                                # File doesn't exist - download
                                r = self.session.get(f"{self.target}{file_url}", stream=True, timeout=30)

                                downloaded = 0

                                with open(file_path, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=8192):
                                        f.write(chunk)
                                        downloaded += len(chunk)

                                size_str = self._format_size(downloaded)
                                print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}✓ {filename} ({size_str}){Colors.RESET}")
                                total_downloaded += 1
                                total_size += downloaded

                            except Exception as e:
                                print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}✗ {filename} (error){Colors.RESET}")
                                if file_path.exists():
                                    file_path.unlink()

                    # Create README.md for the challenge (like ctfd_parser.py)
                    try:
                        readme_path = challenge_dir / "README.md"

                        # Build README content
                        readme_content = f"# {name}\n\n"
                        readme_content += f"**Category:** {category}\n"
                        readme_content += f"**Points:** {challenge.get('value', chall_data.get('value', 'N/A'))}\n\n"

                        # Add description
                        if chall_data.get('description'):
                            readme_content += f"{chall_data['description']}\n\n"

                        # Add connection info if available
                        if chall_data.get('connection_info'):
                            readme_content += f"{chall_data['connection_info']}\n\n"

                        # Add files list
                        if files:
                            readme_content += "## Files:\n\n"
                            for f in files:
                                fname = f.split('?')[0].split('/')[-1] if '?' in f else f.split('/')[-1]
                                readme_content += f" - [{fname}](./{fname})\n"
                            readme_content += "\n"

                        # Write README
                        with open(readme_path, 'w', encoding='utf-8') as f:
                            f.write(readme_content)

                        readme_size = readme_path.stat().st_size
                        print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}✓ README.md ({self._format_size(readme_size)}){Colors.RESET}")

                    except Exception as e:
                        if self.verbose:
                            print(f"  {cat_color}│{Colors.RESET}    {Colors.DIM}✗ README.md (error){Colors.RESET}")

                except Exception as e:
                    if self.verbose:
                        print(f"  {Colors.RED}[!] Error: {e}{Colors.RESET}")

            print(f"  {cat_color}└{Colors.RESET}")
            print()

        print()
        
        # Auto-save status to output directory (silent, no message)
        save_path = Path(output_dir) / "ctfd_status.json"
        try:
            data = {
                'timestamp': datetime.now().isoformat(),
                'target': self.target,
                'username': self.username,
                'summary': {
                    'total': self.get_total_count(),
                    'solved': self.get_solved_count(),
                    'unsolved': self.get_total_count() - self.get_solved_count(),
                    'progress_pct': round(100 * self.get_solved_count() / self.get_total_count(), 2) if self.get_total_count() > 0 else 0
                },
                'categories': {},
                'challenges': []
            }
            
            # Group by category
            for cat in sorted(self.categories.keys()):
                cat_challs = self.categories[cat]
                cat_solved = sum(1 for c in cat_challs if c.get('solved_by_me'))
                data['categories'][cat] = {
                    'total': len(cat_challs),
                    'solved': cat_solved,
                    'progress_pct': round(100 * cat_solved / len(cat_challs), 2) if len(cat_challs) > 0 else 0
                }
            
            # Add all challenges
            for c in sorted(self.challenges, key=lambda x: (-x['solves'], x['name'])):
                data['challenges'].append({
                    'id': c['id'],
                    'name': c['name'],
                    'category': c.get('category', 'Unknown'),
                    'solves': c['solves'],
                    'value': c.get('value', c.get('points', 0)),
                    'solved_by_me': c.get('solved_by_me', False)
                })
            
            with open(save_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _format_size(self, size_bytes):
        """Format file size in human readable format"""
        if size_bytes < 1024:
            return f"{size_bytes:.0f}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f}KB"
        else:
            return f"{size_bytes/1024/1024:.2f}MB"
    
    def submit_flag(self, challenge_name, flag, no_notify=False):
        """Submit a flag"""
        challenge = self.find_challenge(challenge_name)

        if not challenge:
            print(f"\n{Colors.RED}[!] Challenge '{challenge_name}' not found{Colors.RESET}\n")
            return False

        category = challenge.get('category', 'Unknown')
        chall_name = challenge['name']
        chall_id = challenge['id']
        solves = challenge.get('solves', 0)

        print(f"\n{Colors.CYAN}Challenge:{Colors.RESET} [{category}] {chall_name}")
        print(f"{Colors.CYAN}Solves:{Colors.RESET} {solves}")
        print(f"{Colors.CYAN}Flag:{Colors.RESET} {flag}")
        print()

        # Check if already solved
        if challenge.get('solved_by_me'):
            print(f"{Colors.YELLOW}[!] Challenge already solved{Colors.RESET}\n")
            self.send_notification(category, chall_name, "already_solved", no_notify)
            return True

        # Get CSRF token from challenge page
        csrf_token = None
        try:
            r = self.session.get(f"{self.target}/challenges/{chall_id}", timeout=10)
            csrf_match = re.search(b"""'csrfNonce':[ \t]+"([a-f0-9A-F]+)""", r.content)
            if csrf_match:
                csrf_token = csrf_match.group(1).decode()
        except Exception as e:
            if self.verbose:
                print(f"{Colors.DIM}[!] CSRF token error: {e}{Colors.RESET}")

        # Submit with CSRF token
        try:
            headers = {}
            if csrf_token:
                headers['Csrf-Token'] = csrf_token
            
            r = self.session.post(
                self.target + "/api/v1/challenges/attempt",
                json={"challenge_id": chall_id, "submission": flag},
                headers=headers,
                timeout=10
            )

            if r.status_code == 200:
                result = json.loads(r.content)

                if result.get('success'):
                    # Check the actual status
                    status = result.get('data', {}).get('status', '')
                    
                    if status == 'correct':
                        print()
                        print(f"{Colors.GREEN}{'═' * 70}{Colors.RESET}")
                        print(f"{Colors.GREEN}{Colors.BOLD}  FLAG CORRECT!{Colors.RESET}")
                        print(f"{Colors.GREEN}{'═' * 70}{Colors.RESET}")
                        print(f"{Colors.GREEN}  Challenge: [{category}] {chall_name}{Colors.RESET}")
                        print(f"{Colors.GREEN}  Flag: {flag}{Colors.RESET}")
                        print(f"{Colors.GREEN}{'═' * 70}{Colors.RESET}")
                        print()
                        self.send_notification(category, chall_name, "correct", no_notify)
                        return True
                    else:
                        # Submission accepted but incorrect
                        error_msg = result.get('data', {}).get('message', 'Incorrect')
                        print()
                        print(f"{Colors.RED}{'═' * 70}{Colors.RESET}")
                        print(f"{Colors.RED}{Colors.BOLD}  FLAG INCORRECT{Colors.RESET}")
                        print(f"{Colors.RED}{'═' * 70}{Colors.RESET}")
                        print(f"{Colors.RED}  Challenge: [{category}] {chall_name}{Colors.RESET}")
                        print(f"{Colors.RED}  Flag: {flag}{Colors.RESET}")
                        print(f"{Colors.RED}  Message: {error_msg}{Colors.RESET}")
                        print(f"{Colors.RED}{'═' * 70}{Colors.RESET}")
                        print()
                        self.send_notification(category, chall_name, "incorrect", no_notify)
                        return False
                else:
                    print()
                    print(f"{Colors.RED}{'═' * 70}{Colors.RESET}")
                    print(f"{Colors.RED}{Colors.BOLD}  SUBMISSION FAILED{Colors.RESET}")
                    print(f"{Colors.RED}{'═' * 70}{Colors.RESET}")
                    print(f"{Colors.RED}  Challenge: [{category}] {chall_name}{Colors.RESET}")
                    print(f"{Colors.RED}  Flag: {flag}{Colors.RESET}")
                    print(f"{Colors.RED}{'═' * 70}{Colors.RESET}")
                    print()
                    self.send_notification(category, chall_name, "incorrect", no_notify)
                    return False
            else:
                print(f"{Colors.RED}[!] HTTP Error: {r.status_code}{Colors.RESET}\n")
                return False

        except Exception as e:
            print(f"{Colors.RED}[!] Submission error: {e}{Colors.RESET}\n")
            return False
    
    def send_notification(self, category, name, status, no_notify=False):
        """Send desktop and KDE Connect notification"""
        import subprocess

        if no_notify:
            return

        try:
            # Desktop notification
            if status == "correct":
                msg = f"[{category}] {name} - SOLVED"
            elif status == "incorrect":
                msg = f"[{category}] {name} - Incorrect"
            else:
                msg = f"[{category}] {name} - Already solved"

            subprocess.run([
                "notify-send", "-u", "normal" if status == "correct" else "critical",
                "-i", "dialog-information", "CTF Submission", msg
            ], capture_output=True, timeout=5)

            # KDE Connect
            result = subprocess.run(
                ["kdeconnect-cli", "--id-only", "--list-available"],
                capture_output=True, text=True, timeout=5
            )
            devices = [d.strip() for d in result.stdout.strip().split('\n') if d.strip()]

            for device_id in devices:
                subprocess.run([
                    "kdeconnect-cli", "--device", device_id,
                    "--ping-msg", f"CTF: {msg}"
                ], capture_output=True, timeout=5)

        except Exception as e:
            if self.verbose:
                print(f"{Colors.DIM}[!] Notification error: {e}{Colors.RESET}")


class ColoredHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom help formatter - compact layout with green short flags"""
    
    def _format_action(self, action):
        # Get the default formatted action string
        parts = super()._format_action(action)
        
        # Remove extra blank lines (make compact)
        lines = parts.split('\n')
        filtered_lines = [line for line in lines if line.strip()]
        
        # Add green color to short flags only (-X)
        colored_lines = []
        for line in filtered_lines:
            import re
            # Match short flags and color them green
            colored_line = re.sub(
                r'(\s{2,})(-[a-zA-Z])(,?\s+--[\w-]+)?',
                lambda m: f'{m.group(1)}{Colors.GREEN}{m.group(2)}{Colors.RESET}{m.group(3) or ""}',
                line
            )
            colored_lines.append(colored_line)
        
        return '\n'.join(colored_lines) + '\n'


def parse_arguments():
    # Get script name dynamically from how it was invoked
    script_name = os.path.basename(sys.argv[0])

    parser = argparse.ArgumentParser(
        prog=script_name,
        description='CTFd Toolkit - Complete CTF Management Tool',
        formatter_class=ColoredHelpFormatter,
        epilog=f'''
Examples:
  {script_name} -u https://ctf.example.com -U user -P pass --status
  {script_name} -u https://ctf.example.com -U user -P pass --list
  {script_name} -u https://ctf.example.com -U user -P pass --unsolved
  {script_name} -u https://ctf.example.com -U user -P pass --list -c Crypto
  {script_name} -u https://ctf.example.com -U user -P pass --download
  {script_name} -u https://ctf.example.com -U user -P pass --download -c Crypto
  {script_name} -u https://ctf.example.com -U user -P pass --submit -C "Challenge" -f "flag{{}}"
  {script_name} -u https://ctf.example.com -U user -P pass --clear-cache

Environment Variables:
  CTFD_URL      Default target URL
  CTFD_USER     Default username
  CTFD_PASS     Default password
        '''
    )

    # Action arguments
    parser.add_argument(
        '-s', '--status',
        action='store_true',
        help='Show overall challenge status'
    )
    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='List all challenges'
    )
    parser.add_argument(
        '-S', '--unsolved',
        action='store_true',
        help='List unsolved challenges'
    )
    parser.add_argument(
        '--submit',
        action='store_true',
        help='Submit a flag (or use -C and -f together)'
    )
    parser.add_argument(
        '-d', '--download',
        action='store_true',
        help='Download challenge files'
    )
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear cached session'
    )

    # Submit/Challenge arguments
    parser.add_argument(
        '-C', '--challenge',
        type=str,
        help='Challenge name (use with -f to submit flag)'
    )
    parser.add_argument(
        '-f', '--flag',
        type=str,
        help='Flag to submit (use with -C)'
    )

    # Filter arguments
    parser.add_argument(
        '-c', '--category',
        type=str,
        help='Filter by category (for --list, --unsolved, --download)'
    )

    # Download arguments
    parser.add_argument(
        '-o', '--output',
        type=str,
        default='./',
        help='Output directory for downloads (default: ./)'
    )

    # Auth arguments (using familiar names like curl/wget)
    parser.add_argument(
        '-u', '--url',
        type=str,
        dest='target',
        default=None,
        help='CTFd target URL (required)'
    )
    parser.add_argument(
        '-U', '--user', '--username',
        type=str,
        dest='username',
        default=None,
        help='Username (or CTFD_USER env)'
    )
    parser.add_argument(
        '-P', '--password',
        type=str,
        dest='password',
        default=None,
        help='Password (or CTFD_PASS env)'
    )

    # Other options
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable session caching'
    )
    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='Disable notifications'
    )

    args = parser.parse_args()

    # Validate: if --submit is used, -C and -f are required
    if args.submit and (not args.challenge or not args.flag):
        parser.error("--submit requires -C (challenge) and -f (flag)")

    return args


def main():
    args = parse_arguments()

    # Handle clear cache (no auth needed)
    if args.clear_cache:
        # Create a dummy manager just for cache clearing
        manager = CTFdManager(DEFAULT_TARGET, "", "", args.verbose, args.no_cache)
        manager.cache.clear()
        print(f"{Colors.GREEN}[+] Session cache cleared{Colors.RESET}\n")
        return

    # Get credentials (with env fallback)
    target = args.target or os.environ.get('CTFD_URL') or os.environ.get('CTFD_TARGET')
    username = args.username or os.environ.get('CTFD_USER')
    password = args.password or os.environ.get('CTFD_PASS')

    # Check required arguments
    if not target:
        print(f"{Colors.RED}[!] Error: Target URL is required (-u or CTFD_URL env){Colors.RESET}\n")
        sys.exit(1)

    if not username:
        username = input("CTFd username: ")

    if not password:
        password = getpass.getpass("CTFd password: ")

    # Initialize manager
    manager = CTFdManager(target, username, password, args.verbose, args.no_cache)

    # Login
    if not manager.login():
        print(f"{Colors.RED}[!] Login failed{Colors.RESET}\n")
        sys.exit(1)

    # Fetch challenges (not needed for clear-cache)
    if not args.clear_cache:
        if not manager.fetch_challenges():
            print(f"{Colors.RED}[!] Failed to fetch challenges{Colors.RESET}\n")
            sys.exit(1)

    # Execute action
    # Auto-trigger download if -o is specified (user specified output directory)
    if args.output and args.output != './':
        # User specified output directory, assume they want to download
        manager.download_files(category_filter=args.category, output_dir=args.output)
    elif args.download:
        # Explicit download request
        manager.download_files(category_filter=args.category, output_dir=args.output)
    elif args.challenge and args.flag:
        # Submit flag (either via --submit or just -C -f together)
        success = manager.submit_flag(args.challenge, args.flag, args.no_notify)
        sys.exit(0 if success else 1)
    elif args.status:
        manager.show_status()
    elif args.list:
        manager.list_challenges(category_filter=args.category)
    elif args.unsolved:
        manager.list_challenges(unsolved_only=True, category_filter=args.category)
    else:
        # Default: show status
        manager.show_status()


if __name__ == "__main__":
    main()