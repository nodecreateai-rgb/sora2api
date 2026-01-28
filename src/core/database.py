"""Database storage layer"""
import asyncpg
import json
from datetime import datetime, date
from typing import Optional, List
from urllib.parse import urlparse
from .models import Token, TokenStats, Task, RequestLog, AdminConfig, ProxyConfig, WatermarkFreeConfig, CacheConfig, GenerationConfig, TokenRefreshConfig, CallLogicConfig, PowProxyConfig

class Database:
    """PostgreSQL database manager"""

    def __init__(self, db_url: str = None):
        import os
        if db_url is None:
            # Get database URL from environment variable or use default
            db_url = os.getenv("DATABASE_URL", "postgresql://postgres:oi3hrankkh5stuhubukkiuzpwf97nv7l@72.60.196.87:5433/postgres")
        
        self.db_url = db_url
        self.pool: Optional[asyncpg.Pool] = None

    def _mask_password(self, url: str) -> str:
        """Mask password in database URL for logging"""
        try:
            parsed = urlparse(url)
            if parsed.password:
                return url.replace(parsed.password, "***")
        except:
            pass
        return url

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create database connection pool"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                self.db_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
        return self.pool

    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def _is_first_startup(self) -> bool:
        """Check if this is the first startup by checking if admin config exists"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM admin_config")
            return count == 0

    def db_exists(self) -> bool:
        """Check if database connection can be established"""
        # For PostgreSQL, we assume it exists if we can connect
        # This is checked during init_db
        return True

    async def _table_exists(self, conn, table_name: str) -> bool:
        """Check if a table exists in the database"""
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_name)
        return result

    async def _column_exists(self, conn, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a table"""
        try:
            result = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_schema = 'public' 
                    AND table_name = $1 
                    AND column_name = $2
                )
            """, table_name, column_name)
            return result
        except:
            return False

    async def _ensure_config_rows(self, conn, config_dict: dict = None):
        """Ensure all config tables have their default rows

        Args:
            conn: Database connection
            config_dict: Configuration dictionary from setting.toml (optional)
        """
        # Ensure config tables exist for Postgres deployments without schema.sql applied
        if not await self._table_exists(conn, "admin_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    admin_username TEXT DEFAULT 'admin',
                    admin_password TEXT DEFAULT 'admin',
                    api_key TEXT DEFAULT 'han1234',
                    error_ban_threshold INTEGER DEFAULT 3,
                    task_retry_enabled BOOLEAN DEFAULT TRUE,
                    task_max_retries INTEGER DEFAULT 3,
                    auto_disable_on_401 BOOLEAN DEFAULT TRUE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT admin_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "admin_sessions"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires_at ON admin_sessions(expires_at)
            """)

        if not await self._table_exists(conn, "proxy_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS proxy_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    proxy_enabled BOOLEAN DEFAULT FALSE,
                    proxy_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT proxy_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "watermark_free_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS watermark_free_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    watermark_free_enabled BOOLEAN DEFAULT FALSE,
                    parse_method TEXT DEFAULT 'third_party',
                    custom_parse_url TEXT,
                    custom_parse_token TEXT,
                    fallback_on_failure BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT watermark_free_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "cache_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    cache_enabled BOOLEAN DEFAULT FALSE,
                    cache_timeout INTEGER DEFAULT 600,
                    cache_base_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT cache_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "generation_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    image_timeout INTEGER DEFAULT 300,
                    video_timeout INTEGER DEFAULT 3000,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT generation_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "token_refresh_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS token_refresh_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    at_auto_refresh_enabled BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT token_refresh_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "call_logic_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS call_logic_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    call_mode TEXT DEFAULT 'default',
                    polling_mode_enabled BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT call_logic_config_single_row CHECK (id = 1)
                )
            """)

        if not await self._table_exists(conn, "pow_proxy_config"):
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS pow_proxy_config (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    pow_proxy_enabled BOOLEAN DEFAULT FALSE,
                    pow_proxy_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT pow_proxy_config_single_row CHECK (id = 1)
                )
            """)
        # Ensure admin_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM admin_config")
        if count == 0:
            # Get admin credentials from config_dict if provided, otherwise use defaults
            admin_username = "admin"
            admin_password = "admin"
            api_key = "han1234"
            error_ban_threshold = 3
            task_retry_enabled = True
            task_max_retries = 3
            auto_disable_on_401 = True

            if config_dict:
                global_config = config_dict.get("global", {})
                admin_username = global_config.get("admin_username", "admin")
                admin_password = global_config.get("admin_password", "admin")
                api_key = global_config.get("api_key", "han1234")

                admin_config = config_dict.get("admin", {})
                error_ban_threshold = admin_config.get("error_ban_threshold", 3)
                task_retry_enabled = admin_config.get("task_retry_enabled", True)
                task_max_retries = admin_config.get("task_max_retries", 3)
                auto_disable_on_401 = admin_config.get("auto_disable_on_401", True)

            await conn.execute("""
                INSERT INTO admin_config (id, admin_username, admin_password, api_key, error_ban_threshold, task_retry_enabled, task_max_retries, auto_disable_on_401)
                VALUES (1, $1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO NOTHING
            """, admin_username, admin_password, api_key, error_ban_threshold, task_retry_enabled, task_max_retries, auto_disable_on_401)

        # Ensure proxy_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM proxy_config")
        if count == 0:
            # Get proxy config from config_dict if provided, otherwise use defaults
            proxy_enabled = False
            proxy_url = None

            if config_dict:
                proxy_config = config_dict.get("proxy", {})
                proxy_enabled = proxy_config.get("proxy_enabled", False)
                proxy_url = proxy_config.get("proxy_url", "")
                # Convert empty string to None
                proxy_url = proxy_url if proxy_url else None

            await conn.execute("""
                INSERT INTO proxy_config (id, proxy_enabled, proxy_url)
                VALUES (1, $1, $2)
                ON CONFLICT (id) DO NOTHING
            """, proxy_enabled, proxy_url)

        # Ensure watermark_free_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM watermark_free_config")
        if count == 0:
            # Get watermark-free config from config_dict if provided, otherwise use defaults
            watermark_free_enabled = False
            parse_method = "third_party"
            custom_parse_url = None
            custom_parse_token = None
            fallback_on_failure = True

            if config_dict:
                watermark_config = config_dict.get("watermark_free", {})
                watermark_free_enabled = watermark_config.get("watermark_free_enabled", False)
                parse_method = watermark_config.get("parse_method", "third_party")
                custom_parse_url = watermark_config.get("custom_parse_url", "")
                custom_parse_token = watermark_config.get("custom_parse_token", "")
                fallback_on_failure = watermark_config.get("fallback_on_failure", True)

                # Convert empty strings to None
                custom_parse_url = custom_parse_url if custom_parse_url else None
                custom_parse_token = custom_parse_token if custom_parse_token else None

            await conn.execute("""
                INSERT INTO watermark_free_config (id, watermark_free_enabled, parse_method, custom_parse_url, custom_parse_token, fallback_on_failure)
                VALUES (1, $1, $2, $3, $4, $5)
                ON CONFLICT (id) DO NOTHING
            """, watermark_free_enabled, parse_method, custom_parse_url, custom_parse_token, fallback_on_failure)

        # Ensure cache_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM cache_config")
        if count == 0:
            # Get cache config from config_dict if provided, otherwise use defaults
            cache_enabled = False
            cache_timeout = 600
            cache_base_url = None

            if config_dict:
                cache_config = config_dict.get("cache", {})
                cache_enabled = cache_config.get("enabled", False)
                cache_timeout = cache_config.get("timeout", 600)
                cache_base_url = cache_config.get("base_url", "")
                # Convert empty string to None
                cache_base_url = cache_base_url if cache_base_url else None

            await conn.execute("""
                INSERT INTO cache_config (id, cache_enabled, cache_timeout, cache_base_url)
                VALUES (1, $1, $2, $3)
                ON CONFLICT (id) DO NOTHING
            """, cache_enabled, cache_timeout, cache_base_url)

        # Ensure generation_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM generation_config")
        if count == 0:
            # Get generation config from config_dict if provided, otherwise use defaults
            image_timeout = 300
            video_timeout = 3000

            if config_dict:
                generation_config = config_dict.get("generation", {})
                image_timeout = generation_config.get("image_timeout", 300)
                video_timeout = generation_config.get("video_timeout", 3000)

            await conn.execute("""
                INSERT INTO generation_config (id, image_timeout, video_timeout)
                VALUES (1, $1, $2)
                ON CONFLICT (id) DO NOTHING
            """, image_timeout, video_timeout)

        # Ensure token_refresh_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM token_refresh_config")
        if count == 0:
            # Get token refresh config from config_dict if provided, otherwise use defaults
            at_auto_refresh_enabled = False

            if config_dict:
                token_refresh_config = config_dict.get("token_refresh", {})
                at_auto_refresh_enabled = token_refresh_config.get("at_auto_refresh_enabled", False)

            await conn.execute("""
                INSERT INTO token_refresh_config (id, at_auto_refresh_enabled)
                VALUES (1, $1)
                ON CONFLICT (id) DO NOTHING
            """, at_auto_refresh_enabled)

        # Ensure call_logic_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM call_logic_config")
        if count == 0:
            call_mode = "default"
            polling_mode_enabled = False

            if config_dict:
                call_logic_config = config_dict.get("call_logic", {})
                call_mode = call_logic_config.get("call_mode", "default")
                if call_mode not in ("default", "polling"):
                    polling_mode_enabled = call_logic_config.get("polling_mode_enabled", False)
                    call_mode = "polling" if polling_mode_enabled else "default"
                else:
                    polling_mode_enabled = call_mode == "polling"

            await conn.execute("""
                INSERT INTO call_logic_config (id, call_mode, polling_mode_enabled)
                VALUES (1, $1, $2)
                ON CONFLICT (id) DO NOTHING
            """, call_mode, polling_mode_enabled)

        # Ensure pow_proxy_config has a row
        count = await conn.fetchval("SELECT COUNT(*) FROM pow_proxy_config")
        if count == 0:
            pow_proxy_enabled = False
            pow_proxy_url = None

            if config_dict:
                pow_proxy_config = config_dict.get("pow_proxy", {})
                pow_proxy_enabled = pow_proxy_config.get("pow_proxy_enabled", False)
                pow_proxy_url = pow_proxy_config.get("pow_proxy_url", "")
                pow_proxy_url = pow_proxy_url if pow_proxy_url else None

            await conn.execute("""
                INSERT INTO pow_proxy_config (id, pow_proxy_enabled, pow_proxy_url)
                VALUES (1, $1, $2)
                ON CONFLICT (id) DO NOTHING
            """, pow_proxy_enabled, pow_proxy_url)

    async def check_and_migrate_db(self, config_dict: dict = None):
        """Check database integrity and perform migrations if needed

        Args:
            config_dict: Configuration dictionary from setting.toml (optional)
                        Used to initialize new tables with values from setting.toml
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Ensure all config tables have their default rows
            # Pass config_dict if available to initialize from setting.toml
            await self._ensure_config_rows(conn, config_dict)

    async def init_db(self):
        """Initialize database tables - creates all tables and ensures data integrity"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Note: Tables should be created using schema.sql
            # This method just ensures config rows exist
            await self._ensure_config_rows(conn, config_dict=None)

    async def init_config_from_toml(self, config_dict: dict, is_first_startup: bool = True):
        """
        Initialize database configuration from setting.toml

        Args:
            config_dict: Configuration dictionary from setting.toml
            is_first_startup: If True, initialize all config rows from setting.toml.
                            If False (upgrade mode), only ensure missing config rows exist with default values.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if is_first_startup:
                # First startup: Initialize all config tables with values from setting.toml
                await self._ensure_config_rows(conn, config_dict)
            else:
                # Upgrade mode: Only ensure missing config rows exist (with default values, not from TOML)
                await self._ensure_config_rows(conn, config_dict=None)

    # Token operations
    async def add_token(self, token: Token) -> int:
        """Add a new token"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                token_id = await conn.fetchval("""
                    INSERT INTO tokens (token, email, username, name, st, rt, client_id, proxy_url, remark, expiry_time, is_active,
                                       plan_type, plan_title, subscription_end, sora2_supported, sora2_invite_code,
                                       sora2_redeemed_count, sora2_total_count, sora2_remaining_count, sora2_cooldown_until,
                                       image_enabled, video_enabled, image_concurrency, video_concurrency)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
                    RETURNING id
                """, token.token, token.email, "", token.name, token.st, token.rt, token.client_id, token.proxy_url,
                      token.remark, token.expiry_time, token.is_active,
                      token.plan_type, token.plan_title, token.subscription_end,
                      token.sora2_supported, token.sora2_invite_code,
                      token.sora2_redeemed_count, token.sora2_total_count,
                      token.sora2_remaining_count, token.sora2_cooldown_until,
                      token.image_enabled, token.video_enabled,
                      token.image_concurrency, token.video_concurrency)

                # Create stats entry
                await conn.execute("""
                    INSERT INTO token_stats (token_id) VALUES ($1)
                """, token_id)

                return token_id
    
    async def get_token(self, token_id: int) -> Optional[Token]:
        """Get token by ID"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tokens WHERE id = $1", token_id)
            if row:
                return Token(**dict(row))
            return None
    
    async def get_token_by_value(self, token: str) -> Optional[Token]:
        """Get token by value"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tokens WHERE token = $1", token)
            if row:
                return Token(**dict(row))
            return None

    async def get_token_by_email(self, email: str) -> Optional[Token]:
        """Get token by email"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tokens WHERE email = $1", email)
            if row:
                return Token(**dict(row))
            return None
    
    async def get_active_tokens(self) -> List[Token]:
        """Get all active tokens (enabled, not cooled down, not expired)"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM tokens
                WHERE is_active = TRUE
                AND (cooled_until IS NULL OR cooled_until < CURRENT_TIMESTAMP)
                AND (expiry_time IS NULL OR expiry_time > CURRENT_TIMESTAMP)
                ORDER BY last_used_at ASC NULLS FIRST
            """)
            return [Token(**dict(row)) for row in rows]
    
    async def get_all_tokens(self) -> List[Token]:
        """Get all tokens"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM tokens ORDER BY created_at DESC")
            return [Token(**dict(row)) for row in rows]
    
    async def update_token_usage(self, token_id: int):
        """Update token usage"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens 
                SET last_used_at = CURRENT_TIMESTAMP, use_count = use_count + 1
                WHERE id = $1
            """, token_id)
    
    async def update_token_status(self, token_id: int, is_active: bool):
        """Update token status"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens SET is_active = $1 WHERE id = $2
            """, is_active, token_id)

    async def mark_token_expired(self, token_id: int):
        """Mark token as expired and disable it"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens SET is_expired = TRUE, is_active = FALSE WHERE id = $1
            """, token_id)

    async def clear_token_expired(self, token_id: int):
        """Clear token expired flag"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens SET is_expired = FALSE WHERE id = $1
            """, token_id)

    async def update_token_sora2(self, token_id: int, supported: bool, invite_code: Optional[str] = None,
                                redeemed_count: int = 0, total_count: int = 0, remaining_count: int = 0):
        """Update token Sora2 support info"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens
                SET sora2_supported = $1, sora2_invite_code = $2, sora2_redeemed_count = $3, sora2_total_count = $4, sora2_remaining_count = $5
                WHERE id = $6
            """, supported, invite_code, redeemed_count, total_count, remaining_count, token_id)

    async def update_token_sora2_remaining(self, token_id: int, remaining_count: int):
        """Update token Sora2 remaining count"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens SET sora2_remaining_count = $1 WHERE id = $2
            """, remaining_count, token_id)

    async def update_token_sora2_cooldown(self, token_id: int, cooldown_until: Optional[datetime]):
        """Update token Sora2 cooldown time"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens SET sora2_cooldown_until = $1 WHERE id = $2
            """, cooldown_until, token_id)

    async def update_token_cooldown(self, token_id: int, cooled_until: datetime):
        """Update token cooldown"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE tokens SET cooled_until = $1 WHERE id = $2
            """, cooled_until, token_id)
    
    async def delete_token(self, token_id: int):
        """Delete token"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM token_stats WHERE token_id = $1", token_id)
                await conn.execute("DELETE FROM tokens WHERE id = $1", token_id)

    async def update_token(self, token_id: int,
                          token: Optional[str] = None,
                          st: Optional[str] = None,
                          rt: Optional[str] = None,
                          client_id: Optional[str] = None,
                          proxy_url: Optional[str] = None,
                          remark: Optional[str] = None,
                          expiry_time: Optional[datetime] = None,
                          plan_type: Optional[str] = None,
                          plan_title: Optional[str] = None,
                          subscription_end: Optional[datetime] = None,
                          image_enabled: Optional[bool] = None,
                          video_enabled: Optional[bool] = None,
                          image_concurrency: Optional[int] = None,
                          video_concurrency: Optional[int] = None):
        """Update token (AT, ST, RT, client_id, proxy_url, remark, expiry_time, subscription info, image_enabled, video_enabled)"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Build dynamic update query
            updates = []
            params = []
            param_num = 1

            if token is not None:
                updates.append(f"token = ${param_num}")
                params.append(token)
                param_num += 1

            if st is not None:
                updates.append(f"st = ${param_num}")
                params.append(st)
                param_num += 1

            if rt is not None:
                updates.append(f"rt = ${param_num}")
                params.append(rt)
                param_num += 1

            if client_id is not None:
                updates.append(f"client_id = ${param_num}")
                params.append(client_id)
                param_num += 1

            if proxy_url is not None:
                updates.append(f"proxy_url = ${param_num}")
                params.append(proxy_url)
                param_num += 1

            if remark is not None:
                updates.append(f"remark = ${param_num}")
                params.append(remark)
                param_num += 1

            if expiry_time is not None:
                updates.append(f"expiry_time = ${param_num}")
                params.append(expiry_time)
                param_num += 1

            if plan_type is not None:
                updates.append(f"plan_type = ${param_num}")
                params.append(plan_type)
                param_num += 1

            if plan_title is not None:
                updates.append(f"plan_title = ${param_num}")
                params.append(plan_title)
                param_num += 1

            if subscription_end is not None:
                updates.append(f"subscription_end = ${param_num}")
                params.append(subscription_end)
                param_num += 1

            if image_enabled is not None:
                updates.append(f"image_enabled = ${param_num}")
                params.append(image_enabled)
                param_num += 1

            if video_enabled is not None:
                updates.append(f"video_enabled = ${param_num}")
                params.append(video_enabled)
                param_num += 1

            if image_concurrency is not None:
                updates.append(f"image_concurrency = ${param_num}")
                params.append(image_concurrency)
                param_num += 1

            if video_concurrency is not None:
                updates.append(f"video_concurrency = ${param_num}")
                params.append(video_concurrency)
                param_num += 1

            if updates:
                params.append(token_id)
                query = f"UPDATE tokens SET {', '.join(updates)} WHERE id = ${param_num}"
                await conn.execute(query, *params)

    # Token stats operations
    async def get_token_stats(self, token_id: int) -> Optional[TokenStats]:
        """Get token statistics"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM token_stats WHERE token_id = $1", token_id)
            if row:
                row_dict = dict(row)
                # Convert date object to string if present
                if row_dict.get('today_date') and isinstance(row_dict['today_date'], date):
                    row_dict['today_date'] = row_dict['today_date'].isoformat()
                return TokenStats(**row_dict)
            return None
    
    async def increment_image_count(self, token_id: int):
        """Increment image generation count"""
        from datetime import date
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            today = date.today()
            # Get current stats
            row = await conn.fetchrow("SELECT today_date FROM token_stats WHERE token_id = $1", token_id)

            # If date changed, reset today's count
            if row and row['today_date'] != today:
                await conn.execute("""
                    UPDATE token_stats
                    SET image_count = image_count + 1,
                        today_image_count = 1,
                        today_date = $1
                    WHERE token_id = $2
                """, today, token_id)
            else:
                # Same day, just increment both
                await conn.execute("""
                    UPDATE token_stats
                    SET image_count = image_count + 1,
                        today_image_count = today_image_count + 1,
                        today_date = $1
                    WHERE token_id = $2
                """, today, token_id)

    async def increment_video_count(self, token_id: int):
        """Increment video generation count"""
        from datetime import date
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            today = date.today()
            # Get current stats
            row = await conn.fetchrow("SELECT today_date FROM token_stats WHERE token_id = $1", token_id)

            # If date changed, reset today's count
            if row and row['today_date'] != today:
                await conn.execute("""
                    UPDATE token_stats
                    SET video_count = video_count + 1,
                        today_video_count = 1,
                        today_date = $1
                    WHERE token_id = $2
                """, today, token_id)
            else:
                # Same day, just increment both
                await conn.execute("""
                    UPDATE token_stats
                    SET video_count = video_count + 1,
                        today_video_count = today_video_count + 1,
                        today_date = $1
                    WHERE token_id = $2
                """, today, token_id)
    
    async def increment_error_count(self, token_id: int, increment_consecutive: bool = True):
        """Increment error count

        Args:
            token_id: Token ID
            increment_consecutive: Whether to increment consecutive error count (False for overload errors)
        """
        from datetime import date
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            today = date.today()
            # Get current stats
            row = await conn.fetchrow("SELECT today_date FROM token_stats WHERE token_id = $1", token_id)

            # If date changed, reset today's error count
            if row and row['today_date'] != today:
                if increment_consecutive:
                    await conn.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            consecutive_error_count = consecutive_error_count + 1,
                            today_error_count = 1,
                            today_date = $1,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = $2
                    """, today, token_id)
                else:
                    await conn.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            today_error_count = 1,
                            today_date = $1,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = $2
                    """, today, token_id)
            else:
                # Same day, just increment counters
                if increment_consecutive:
                    await conn.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            consecutive_error_count = consecutive_error_count + 1,
                            today_error_count = today_error_count + 1,
                            today_date = $1,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = $2
                    """, today, token_id)
                else:
                    await conn.execute("""
                        UPDATE token_stats
                        SET error_count = error_count + 1,
                            today_error_count = today_error_count + 1,
                            today_date = $1,
                            last_error_at = CURRENT_TIMESTAMP
                        WHERE token_id = $2
                    """, today, token_id)
    
    async def reset_error_count(self, token_id: int):
        """Reset consecutive error count (keep total error_count)"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE token_stats SET consecutive_error_count = 0 WHERE token_id = $1
            """, token_id)
    
    # Task operations
    async def create_task(self, task: Task) -> int:
        """Create a new task"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            task_id = await conn.fetchval("""
                INSERT INTO tasks (task_id, token_id, model, prompt, status, progress, retry_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """, task.task_id, task.token_id, task.model, task.prompt, task.status, task.progress, task.retry_count)
            return task_id
    
    async def update_task(self, task_id: str, status: str, progress: float, 
                         result_urls: Optional[str] = None, error_message: Optional[str] = None):
        """Update task status"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            completed_at = datetime.now() if status in ["completed", "failed"] else None
            await conn.execute("""
                UPDATE tasks 
                SET status = $1, progress = $2, result_urls = $3, error_message = $4, completed_at = $5
                WHERE task_id = $6
            """, status, progress, result_urls, error_message, completed_at, task_id)
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM tasks WHERE task_id = $1", task_id)
            if row:
                return Task(**dict(row))
            return None
    
    # Request log operations
    async def log_request(self, log: RequestLog) -> int:
        """Log a request and return log ID"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            log_id = await conn.fetchval("""
                INSERT INTO request_logs (token_id, task_id, operation, request_body, response_body, status_code, duration)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
            """, log.token_id, log.task_id, log.operation, log.request_body, log.response_body,
                  log.status_code, log.duration)
            return log_id

    async def update_request_log(self, log_id: int, response_body: Optional[str] = None,
                                 status_code: Optional[int] = None, duration: Optional[float] = None,
                                 token_id: Optional[int] = None, task_id: Optional[str] = None):
        """Update request log with completion data"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            updates = []
            params = []
            param_num = 1

            if response_body is not None:
                updates.append(f"response_body = ${param_num}")
                params.append(response_body)
                param_num += 1
            if status_code is not None:
                updates.append(f"status_code = ${param_num}")
                params.append(status_code)
                param_num += 1
            if duration is not None:
                updates.append(f"duration = ${param_num}")
                params.append(duration)
                param_num += 1
            if token_id is not None:
                updates.append(f"token_id = ${param_num}")
                params.append(token_id)
                param_num += 1
            if task_id is not None:
                updates.append(f"task_id = ${param_num}")
                params.append(task_id)
                param_num += 1

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(log_id)
                query = f"UPDATE request_logs SET {', '.join(updates)} WHERE id = ${param_num}"
                await conn.execute(query, *params)

    async def update_request_log_task_id(self, log_id: int, task_id: str):
        """Update request log task_id by log_id"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE request_logs SET task_id = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
            """, task_id, log_id)
    
    async def update_request_log_by_task_id(self, task_id: str, response_body: Optional[str] = None,
                                           status_code: Optional[int] = None, duration: Optional[float] = None):
        """Update request log by task_id"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            updates = []
            params = []
            param_num = 1

            if response_body is not None:
                updates.append(f"response_body = ${param_num}")
                params.append(response_body)
                param_num += 1
            if status_code is not None:
                updates.append(f"status_code = ${param_num}")
                params.append(status_code)
                param_num += 1
            if duration is not None:
                updates.append(f"duration = ${param_num}")
                params.append(duration)
                param_num += 1

            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                params.append(task_id)
                query = f"UPDATE request_logs SET {', '.join(updates)} WHERE task_id = ${param_num}"
                await conn.execute(query, *params)
    
    async def get_recent_logs(self, limit: int = 100) -> List[dict]:
        """Get recent logs with token email"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT
                    rl.id,
                    rl.token_id,
                    rl.task_id,
                    rl.operation,
                    rl.request_body,
                    rl.response_body,
                    rl.status_code,
                    rl.duration,
                    rl.created_at,
                    t.email as token_email,
                    t.username as token_username
                FROM request_logs rl
                LEFT JOIN tokens t ON rl.token_id = t.id
                ORDER BY rl.created_at DESC
                LIMIT $1
            """, limit)
            return [dict(row) for row in rows]

    async def clear_all_logs(self):
        """Clear all request logs"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM request_logs")

    # Admin config operations
    async def get_admin_config(self) -> AdminConfig:
        """Get admin configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM admin_config WHERE id = 1")
            if row:
                return AdminConfig(**dict(row))
            # If no row exists, return a default config with placeholder values
            # This should not happen in normal operation as _ensure_config_rows should create it
            return AdminConfig(admin_username="admin", admin_password="admin", api_key="han1234")
    
    async def update_admin_config(self, config: AdminConfig):
        """Update admin configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE admin_config
                SET admin_username = $1, admin_password = $2, api_key = $3, error_ban_threshold = $4,
                    task_retry_enabled = $5, task_max_retries = $6, auto_disable_on_401 = $7,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, config.admin_username, config.admin_password, config.api_key, config.error_ban_threshold,
                 config.task_retry_enabled, config.task_max_retries, config.auto_disable_on_401)
    
    # Admin session operations
    async def create_admin_session(self, token: str, expires_at: Optional[datetime] = None):
        """Create a new admin session"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO admin_sessions (token, expires_at)
                VALUES ($1, $2)
                ON CONFLICT (token) DO UPDATE
                SET last_used_at = CURRENT_TIMESTAMP, expires_at = $2
            """, token, expires_at)
    
    async def get_admin_session(self, token: str) -> Optional[dict]:
        """Get admin session by token"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM admin_sessions
                WHERE token = $1
                AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """, token)
            if row:
                return dict(row)
            return None
    
    async def update_admin_session_last_used(self, token: str):
        """Update admin session last used time"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE admin_sessions
                SET last_used_at = CURRENT_TIMESTAMP
                WHERE token = $1
            """, token)
    
    async def delete_admin_session(self, token: str):
        """Delete admin session"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM admin_sessions WHERE token = $1", token)
    
    async def cleanup_expired_admin_sessions(self):
        """Clean up expired admin sessions"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM admin_sessions WHERE expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP")
    
    # Proxy config operations
    async def get_proxy_config(self) -> ProxyConfig:
        """Get proxy configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM proxy_config WHERE id = 1")
            if row:
                return ProxyConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return ProxyConfig(proxy_enabled=False)
    
    async def update_proxy_config(self, enabled: bool, proxy_url: Optional[str]):
        """Update proxy configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE proxy_config
                SET proxy_enabled = $1, proxy_url = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, enabled, proxy_url)

    # Watermark-free config operations
    async def get_watermark_free_config(self) -> WatermarkFreeConfig:
        """Get watermark-free configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM watermark_free_config WHERE id = 1")
            if row:
                return WatermarkFreeConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return WatermarkFreeConfig(watermark_free_enabled=False, parse_method="third_party")

    async def update_watermark_free_config(self, enabled: bool, parse_method: str = None,
                                          custom_parse_url: str = None, custom_parse_token: str = None,
                                          fallback_on_failure: Optional[bool] = None):
        """Update watermark-free configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if parse_method is None and custom_parse_url is None and custom_parse_token is None and fallback_on_failure is None:
                # Only update enabled status
                await conn.execute("""
                    UPDATE watermark_free_config
                    SET watermark_free_enabled = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, enabled)
            else:
                # Update all fields
                await conn.execute("""
                    UPDATE watermark_free_config
                    SET watermark_free_enabled = $1, parse_method = $2, custom_parse_url = $3,
                        custom_parse_token = $4, fallback_on_failure = $5, updated_at = CURRENT_TIMESTAMP
                    WHERE id = 1
                """, enabled, parse_method or "third_party", custom_parse_url, custom_parse_token,
                     fallback_on_failure if fallback_on_failure is not None else True)

    # Cache config operations
    async def get_cache_config(self) -> CacheConfig:
        """Get cache configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM cache_config WHERE id = 1")
            if row:
                return CacheConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return CacheConfig(cache_enabled=False, cache_timeout=600)

    async def update_cache_config(self, enabled: bool = None, timeout: int = None, base_url: Optional[str] = None):
        """Update cache configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Get current config first
            row = await conn.fetchrow("SELECT * FROM cache_config WHERE id = 1")

            if row:
                current = dict(row)
                # Update only provided fields
                new_enabled = enabled if enabled is not None else current.get("cache_enabled", False)
                new_timeout = timeout if timeout is not None else current.get("cache_timeout", 600)
                new_base_url = base_url if base_url is not None else current.get("cache_base_url")
            else:
                new_enabled = enabled if enabled is not None else False
                new_timeout = timeout if timeout is not None else 600
                new_base_url = base_url

            # Convert empty string to None
            new_base_url = new_base_url if new_base_url else None

            await conn.execute("""
                UPDATE cache_config
                SET cache_enabled = $1, cache_timeout = $2, cache_base_url = $3, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, new_enabled, new_timeout, new_base_url)

    # Generation config operations
    async def get_generation_config(self) -> GenerationConfig:
        """Get generation configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM generation_config WHERE id = 1")
            if row:
                return GenerationConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return GenerationConfig(image_timeout=300, video_timeout=3000)

    async def update_generation_config(self, image_timeout: int = None, video_timeout: int = None):
        """Update generation configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            # Get current config first
            row = await conn.fetchrow("SELECT * FROM generation_config WHERE id = 1")

            if row:
                current = dict(row)
                # Update only provided fields
                new_image_timeout = image_timeout if image_timeout is not None else current.get("image_timeout", 300)
                new_video_timeout = video_timeout if video_timeout is not None else current.get("video_timeout", 3000)
            else:
                new_image_timeout = image_timeout if image_timeout is not None else 300
                new_video_timeout = video_timeout if video_timeout is not None else 3000

            await conn.execute("""
                UPDATE generation_config
                SET image_timeout = $1, video_timeout = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, new_image_timeout, new_video_timeout)

    # Token refresh config operations
    async def get_token_refresh_config(self) -> TokenRefreshConfig:
        """Get token refresh configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM token_refresh_config WHERE id = 1")
            if row:
                return TokenRefreshConfig(**dict(row))
            # If no row exists, return a default config
            # This should not happen in normal operation as _ensure_config_rows should create it
            return TokenRefreshConfig(at_auto_refresh_enabled=False)

    async def update_token_refresh_config(self, at_auto_refresh_enabled: bool):
        """Update token refresh configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE token_refresh_config
                SET at_auto_refresh_enabled = $1, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, at_auto_refresh_enabled)

    # Call logic config operations
    async def get_call_logic_config(self) -> CallLogicConfig:
        """Get call logic configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM call_logic_config WHERE id = 1")
            if row:
                return CallLogicConfig(**dict(row))
            return CallLogicConfig(call_mode="default", polling_mode_enabled=False)

    async def update_call_logic_config(self, call_mode: str):
        """Update call logic configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            polling_mode_enabled = call_mode == "polling"
            await conn.execute("""
                UPDATE call_logic_config
                SET call_mode = $1, polling_mode_enabled = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, call_mode, polling_mode_enabled)

    # POW proxy config operations
    async def get_pow_proxy_config(self) -> PowProxyConfig:
        """Get POW proxy configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM pow_proxy_config WHERE id = 1")
            if row:
                return PowProxyConfig(**dict(row))
            return PowProxyConfig(pow_proxy_enabled=False, pow_proxy_url=None)

    async def update_pow_proxy_config(self, pow_proxy_enabled: bool, pow_proxy_url: Optional[str] = None):
        """Update POW proxy configuration"""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE pow_proxy_config
                SET pow_proxy_enabled = $1, pow_proxy_url = $2, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
            """, pow_proxy_enabled, pow_proxy_url)
