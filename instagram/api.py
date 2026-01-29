"""
Instagram Bot - GraphQL API Functions
Instagram API bilan ishlash funksiyalari
"""

import time
import json
import urllib.parse
import logging

import config

logger = logging.getLogger(__name__)


class InstagramAPI:
    """Instagram GraphQL API bilan ishlash"""
    
    def __init__(self, page, context=None):
        self.page = page
        self.context = context  # Cookie olish uchun
    
    def get_user_id_via_api(self, username: str) -> str:
        """Username orqali User ID olish (Navigatsiyasiz)"""
        try:
            user_id = self.page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch("https://www.instagram.com/api/v1/users/web_profile_info/?username={username}", {{
                        headers: {{
                            "X-IG-App-ID": "936619743392459",
                            "X-Requested-With": "XMLHttpRequest"
                        }}
                    }});
                    const json = await resp.json();
                    return json.data.user.id;
                }} catch (e) {{
                    return null;
                }}
            }}""")
            return user_id
        except Exception as e:
            return None

    def get_my_user_id(self) -> str:
        """O'z user ID ni olish"""
        try:
            # 0. Cookie dan olish (Eng tez - 0ms)
            if self.context:
                try:
                    cookies = self.context.cookies()
                    for cookie in cookies:
                        if cookie['name'] == 'ds_user_id':
                            return cookie['value']
                except:
                    pass

            self.page.goto(f"https://www.instagram.com/{config.INSTAGRAM_USERNAME}/", 
                          wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            # HTML source dan user_id ni ajratib olish
            user_id = self.page.evaluate("""() => {
                const html = document.documentElement.innerHTML;
                
                // Usul 1: profilePage_XXXXX
                let match = html.match(/"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                // Usul 2: user_id":"XXXXX
                match = html.match(/"user_id":"([0-9]+)"/);
                if (match) return match[1];
                
                // Usul 3: logging_page_id dari
                match = html.match(/"logging_page_id":"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                return null;
            }""")
            
            return user_id
        except Exception as e:
            logger.error(f"❌ User ID olishda xato: {e}")
            return None

    def get_target_user_id(self, target: str) -> str:
        """Target username dan user ID olish"""
        try:
            # 1. API orqali (Navigatsiyasiz - Tez)
            user_id = self.get_user_id_via_api(target)
            if user_id:
                return user_id

            logger.info("⚠️ API ID olinmadi, Browser orqali urinib ko'ramiz...")
            self.page.goto(f"https://www.instagram.com/{target}/", 
                          wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            
            user_id = self.page.evaluate("""() => {
                const html = document.documentElement.innerHTML;
                
                let match = html.match(/"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                match = html.match(/"user_id":"([0-9]+)"/);
                if (match) return match[1];
                
                match = html.match(/"logging_page_id":"profilePage_([0-9]+)"/);
                if (match) return match[1];
                
                return null;
            }""")
            
            return user_id
        except Exception as e:
            logger.error(f"❌ Target User ID olishda xato: {e}")
            return None

    def follow_via_api(self, user_id: str) -> dict:
        """API orqali follow qilish (Tezkor) - Return: {success: bool, error: str}"""
        try:
            result = self.page.evaluate(f"""async () => {{
                try {{
                    // CSRF Token olish
                    const getCookie = (name) => {{
                        const value = `; ${{document.cookie}}`;
                        const parts = value.split(`; ${{name}}=`);
                        if (parts.length === 2) return parts.pop().split(';').shift();
                    }}
                    const csrftoken = getCookie('csrftoken');

                    const resp = await fetch("https://www.instagram.com/api/v1/friendships/create/{user_id}/", {{
                        method: "POST",
                        headers: {{
                            "X-IG-App-ID": "936619743392459",
                            "X-Requested-With": "XMLHttpRequest",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "X-CSRFToken": csrftoken
                        }}
                    }});
                    
                    if (!resp.headers.get("content-type")?.includes("application/json")) {{
                         const text = await resp.text();
                         if (text.includes("login")) return {{ success: false, error: "Login Required (Redirect)" }};
                         return {{ success: false, error: "Non-JSON Response (Challenge/Error)" }};
                    }}

                    const json = await resp.json();
                    if (json.status === "ok" || json.result === "following") {{
                        return {{ success: true }};
                    }} else {{
                        return {{ success: false, error: json.message || json.status || "Unknown error" }};
                    }}
                }} catch (e) {{
                    return {{ success: false, error: e.toString() }};
                }}
            }}""")
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def unfollow_via_api(self, user_id: str) -> dict:
        """API orqali unfollow qilish (Tezkor) - Return: {success: bool, error: str}"""
        try:
            result = self.page.evaluate(f"""async () => {{
                try {{
                    const getCookie = (name) => {{
                        const value = `; ${{document.cookie}}`;
                        const parts = value.split(`; ${{name}}=`);
                        if (parts.length === 2) return parts.pop().split(';').shift();
                    }}
                    const csrftoken = getCookie('csrftoken');

                    const resp = await fetch("https://www.instagram.com/api/v1/friendships/destroy/{user_id}/", {{
                        method: "POST",
                        headers: {{
                            "X-IG-App-ID": "936619743392459",
                            "X-Requested-With": "XMLHttpRequest",
                            "Content-Type": "application/x-www-form-urlencoded",
                            "X-CSRFToken": csrftoken
                        }}
                    }});

                    if (!resp.headers.get("content-type")?.includes("application/json")) {{
                         return {{ success: false, error: "Non-JSON Response (Challenge/Error)" }};
                    }}

                    const json = await resp.json();
                    if (json.status === "ok") {{
                        return {{ success: true }};
                    }} else {{
                        return {{ success: false, error: json.message || "Unknown error" }};
                    }}
                }} catch (e) {{
                    return {{ success: false, error: e.toString() }};
                }}
            }}""")
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fetch_followers_api(self, user_id: str, max_count: int = 1000) -> list:
        """Instagram GraphQL API orqali followers olish"""
        followers = []
        end_cursor = ""
        page_count = 0
        max_pages = 200  # Xavfsizlik limiti (200 * 50 = 10,000 follower)
        
        try:
            while len(followers) < max_count and page_count < max_pages:
                variables = {"id": user_id, "first": 50}
                if end_cursor:
                    variables["after"] = end_cursor
                
                # Query hash - Instagram followers uchun
                query_hash = "c76146de99bb02f6415203be841dd25a"
                url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={urllib.parse.quote(json.dumps(variables))}"
                
                # Fetch qilish (browser context orqali - cookies avtomatik)
                result = self.page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{url}", {{
                            headers: {{
                                "x-requested-with": "XMLHttpRequest"
                            }},
                            credentials: "include"
                        }});
                        return await resp.json();
                    }} catch(e) {{
                        return null;
                    }}
                }}""")
                
                if not result or 'data' not in result:
                    logger.warning(f"⚠️ GraphQL javob yo'q yoki xato")
                    break
                
                edges = result.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('edges', [])
                
                if not edges:
                    logger.info("📭 Boshqa follower yo'q")
                    break
                
                for edge in edges:
                    username = edge.get('node', {}).get('username')
                    if username:
                        followers.append(username)
                
                # Keyingi sahifa
                page_info = result.get('data', {}).get('user', {}).get('edge_followed_by', {}).get('page_info', {})
                has_next = page_info.get('has_next_page', False)
                end_cursor = page_info.get('end_cursor', '')
                
                page_count += 1
                logger.info(f"📊 API Progress: {len(followers)} ta follower ({page_count} sahifa)")
                
                if not has_next:
                    break
                    
                time.sleep(1)  # Rate limit
            
            return followers
            
        except Exception as e:
            logger.error(f"❌ GraphQL API xatosi: {e}")
            return []

    def fetch_following_api(self, user_id: str, max_count: int = 1000) -> list:
        """Instagram GraphQL API orqali FOLLOWING olish (men kimlarni follow qilaman)"""
        following = []
        end_cursor = ""
        page_count = 0
        
        try:
            while len(following) < max_count and page_count < 50:
                variables = {"id": user_id, "first": 50}
                if end_cursor:
                    variables["after"] = end_cursor
                
                # FOLLOWING uchun boshqa query hash
                query_hash = "d04b0a864b4b54837c0d870b0e77e076"  # edge_follow query
                url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={urllib.parse.quote(json.dumps(variables))}"
                
                result = self.page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{url}", {{
                            headers: {{ "x-requested-with": "XMLHttpRequest" }},
                            credentials: "include"
                        }});
                        return await resp.json();
                    }} catch(e) {{
                        return null;
                    }}
                }}""")
                
                if not result or 'data' not in result:
                    logger.warning("⚠️ Following API javob yo'q")
                    break
                
                edges = result.get('data', {}).get('user', {}).get('edge_follow', {}).get('edges', [])
                
                if not edges:
                    break
                
                for edge in edges:
                    username = edge.get('node', {}).get('username')
                    if username:
                        following.append(username)
                
                page_info = result.get('data', {}).get('user', {}).get('edge_follow', {}).get('page_info', {})
                has_next = page_info.get('has_next_page', False)
                end_cursor = page_info.get('end_cursor', '')
                
                page_count += 1
                logger.info(f"📊 Following API: {len(following)} ta ({page_count} sahifa)")
                
                if not has_next:
                    break
                
                time.sleep(1)
            
            return following
            
        except Exception as e:
            logger.error(f"❌ Following API xatosi: {e}")
            return []

    def get_user_info(self, username: str) -> dict:
        """Foydalanuvchi ma'lumotlarini olish (follows_viewer tekshirish uchun)"""
        try:
            profile_json_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            user_info = self.page.evaluate(f"""async () => {{
                try {{
                    const resp = await fetch("{profile_json_url}", {{
                        headers: {{ 
                            "X-IG-App-ID": "936619743392459",
                            "X-Requested-With": "XMLHttpRequest"
                        }}
                    }});
                    const data = await resp.json();
                    return {{
                        id: data.data?.user?.id,
                        follows_viewer: data.data?.user?.follows_viewer,
                        status: data.status,
                        error: data.message
                    }};
                }} catch(e) {{ return {{ error: e.toString() }}; }}
            }}""")
            return user_info
        except Exception as e:
            return {"error": str(e)}
