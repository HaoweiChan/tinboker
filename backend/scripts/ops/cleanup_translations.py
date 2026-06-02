#!/usr/bin/env python3
"""
Cleanup and validate stock translations in the database.

This script:
1. Finds and removes duplicate entries (same ticker with different markets like US vs TW)
2. Detects Chinese text incorrectly placed in name_en column
3. Swaps misplaced name_en ↔ name_zh_tw if detected
4. Cleans English names:
   - Removes legal suffixes (Inc., Corp., Ltd., LLC, NV, PLC, etc.)
   - Normalizes to title case (e.g., "APPLE INC." → "Apple")
5. Reports data quality issues

Usage:
    python scripts/cleanup_translations.py --dry-run   # Preview changes without applying
    python scripts/cleanup_translations.py             # Apply fixes
"""

import sys
import re
import argparse
import logging
from pathlib import Path
from typing import List, Tuple

# Add backend root to path for imports (scripts/ops/ -> backend/)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.postgres import get_session, init_engine, create_all_tables
from src.database import models  # noqa: F401 - Import to register models
from src.database.models import StockTranslation
from sqlalchemy import func

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def contains_chinese(text: str) -> bool:
    """Check if text contains Chinese characters."""
    if not text:
        return False
    # Unicode range for CJK characters
    return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', text))


def contains_only_ascii(text: str) -> bool:
    """Check if text contains only ASCII characters (letters, numbers, punctuation)."""
    if not text:
        return True
    return bool(re.match(r'^[\x00-\x7F]+$', text))


# Legal suffixes to remove from stock names (case-insensitive patterns)
LEGAL_SUFFIXES = [
    r'\bInc\.?$',         # Inc, Inc.
    r'\bCorp\.?$',        # Corp, Corp.
    r'\bCorporation$',    # Corporation
    r'\bLtd\.?$',         # Ltd, Ltd.
    r'\bLimited$',        # Limited
    r'\bLLC$',            # LLC
    r'\bL\.L\.C\.?$',     # L.L.C, L.L.C.
    r'\bPLC$',            # PLC (Public Limited Company)
    r'\bP\.L\.C\.?$',     # P.L.C, P.L.C.
    r'\bNV$',             # NV (Dutch)
    r'\bN\.V\.?$',        # N.V, N.V.
    r'\bS\.A\.?$',        # S.A, S.A. (Société Anonyme)
    r'\bSA$',             # SA
    r'\bAG$',             # AG (German)
    r'\bA\.G\.?$',        # A.G, A.G.
    r'\bGmbH$',           # GmbH (German)
    r'\bCo\.?$',          # Co, Co.
    r'\bCompany$',        # Company
    r'\b& Co\.?$',        # & Co, & Co.
    r'\bHolding$',        # Holding
    r'\bHoldings$',       # Holdings
    r'\bGroup$',          # Group
    r'\bClass [A-Z]$',    # Class A, Class B, etc.
    r'\bCommon Stock$',   # Common Stock
]


def remove_legal_suffixes(name: str) -> str:
    """Remove legal entity suffixes from a stock name."""
    if not name:
        return name
    
    result = name.strip()
    
    # Apply each pattern iteratively (some names may have multiple suffixes)
    for _ in range(3):  # Max 3 iterations to catch nested suffixes
        prev = result
        for pattern in LEGAL_SUFFIXES:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE).strip()
            # Also remove trailing comma if any
            result = re.sub(r',\s*$', '', result).strip()
        if result == prev:
            break
    
    return result


def normalize_title_case(name: str) -> str:
    """
    Normalize name to title case (first letter of each word capitalized).
    Handles edge cases like acronyms and special characters.
    """
    if not name:
        return name
    
    # Words that should remain uppercase (acronyms/abbreviations)
    keep_upper = {'AMD', 'IBM', 'HP', 'AT&T', 'ATT', 'CEO', 'USA', 'UK', 'EU', 'AI', 'IT', 'TV', 'UK', 'NYSE', 'NASDAQ', 'ETF'}
    
    # Words that should remain lowercase (articles, prepositions)
    keep_lower = {'a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'by', 'with', 'de', 'la', 'le', 'du'}
    
    words = name.split()
    result = []
    
    for i, word in enumerate(words):
        # First word always capitalized
        if i == 0:
            if word.upper() in keep_upper:
                result.append(word.upper())
            else:
                result.append(word.capitalize())
        elif word.upper() in keep_upper:
            result.append(word.upper())
        elif word.lower() in keep_lower:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    
    return ' '.join(result)


def clean_english_name(name: str) -> str:
    """Apply all cleaning transformations to an English stock name."""
    if not name:
        return name
    result = remove_legal_suffixes(name)
    result = normalize_title_case(result)
    return result


def find_duplicates(session) -> List[Tuple[str, List[StockTranslation]]]:
    """
    Find tickers that exist in multiple markets (potential duplicates).
    Returns list of (ticker, [translations]) tuples.
    """
    # Find tickers with multiple entries
    duplicates = []
    
    # Group by ticker, find those with > 1 market
    ticker_counts = session.query(
        StockTranslation.ticker,
        func.count(StockTranslation.id).label('count')
    ).group_by(StockTranslation.ticker).having(func.count(StockTranslation.id) > 1).all()
    
    for ticker, count in ticker_counts:
        translations = session.query(StockTranslation).filter(
            StockTranslation.ticker == ticker
        ).all()
        duplicates.append((ticker, translations))
    
    return duplicates


def find_misplaced_chinese(session) -> List[StockTranslation]:
    """Find entries where name_en contains Chinese characters."""
    all_translations = session.query(StockTranslation).all()
    misplaced = []
    
    for t in all_translations:
        if t.name_en and contains_chinese(t.name_en):
            misplaced.append(t)
    
    return misplaced


def find_missing_english_names(session) -> List[StockTranslation]:
    """Find entries where name_en is empty but name_zh_tw exists."""
    return session.query(StockTranslation).filter(
        (StockTranslation.name_en.is_(None) | (StockTranslation.name_en == "")),
        StockTranslation.name_zh_tw.isnot(None),
        StockTranslation.name_zh_tw != ""
    ).all()


def cleanup_duplicates(session, duplicates: List[Tuple[str, List[StockTranslation]]], dry_run: bool = True) -> int:
    """
    Clean up duplicate entries.
    Priority: Keep TW market for TW tickers (numeric), keep US market for US tickers (letters).
    """
    deleted = 0
    
    for ticker, translations in duplicates:
        logger.info(f"\n--- Ticker: {ticker} ({len(translations)} entries) ---")
        
        for t in translations:
            logger.info(f"  [{t.market}] EN: {t.name_en or '(empty)'} | ZH: {t.name_zh_tw or '(empty)'} | Status: {t.translation_status}")
        
        # Determine which to keep
        # If ticker is numeric -> likely TW stock
        # If ticker is alphanumeric -> likely US stock
        is_numeric_ticker = ticker.isdigit()
        
        keep_entry = None
        delete_entries = []
        
        for t in translations:
            # For numeric tickers, prefer TW
            if is_numeric_ticker and t.market == "TW":
                keep_entry = t
            # For alpha tickers, prefer US
            elif not is_numeric_ticker and t.market == "US":
                keep_entry = t
        
        # If no clear preference, keep the one with better data
        if keep_entry is None:
            # Keep entry with both names filled
            for t in translations:
                if t.name_en and t.name_zh_tw and not contains_chinese(t.name_en):
                    keep_entry = t
                    break
        
        # Still no winner? Keep first one
        if keep_entry is None:
            keep_entry = translations[0]
        
        # Mark others for deletion
        for t in translations:
            if t.id != keep_entry.id:
                delete_entries.append(t)
        
        logger.info(f"  ✓ KEEP: [{keep_entry.market}] {keep_entry.name_en or '?'} / {keep_entry.name_zh_tw or '?'}")
        
        for t in delete_entries:
            logger.info(f"  ✗ DELETE: [{t.market}] {t.name_en or '?'} / {t.name_zh_tw or '?'}")
            if not dry_run:
                session.delete(t)
                deleted += 1
    
    return deleted


def fix_misplaced_chinese(session, misplaced: List[StockTranslation], dry_run: bool = True) -> int:
    """
    Fix entries where Chinese text is in the name_en column.
    If name_zh_tw is empty, move name_en to name_zh_tw.
    """
    fixed = 0
    
    for t in misplaced:
        logger.info(f"\n--- Ticker: {t.ticker} [{t.market}] ---")
        logger.info(f"  Current: EN='{t.name_en}' | ZH='{t.name_zh_tw or '(empty)'}'")
        
        # If Chinese is in name_en and name_zh_tw is empty
        if contains_chinese(t.name_en) and not t.name_zh_tw:
            logger.info(f"  → FIX: Move '{t.name_en}' to name_zh_tw, clear name_en")
            if not dry_run:
                t.name_zh_tw = t.name_en
                t.name_en = None
                t.translation_status = "pending"  # Mark for review
                fixed += 1
        
        # If both columns have content and name_en has Chinese
        elif contains_chinese(t.name_en) and t.name_zh_tw:
            # Check if they might be swapped
            if contains_only_ascii(t.name_zh_tw):
                logger.info(f"  → FIX: Swap - name_en='{t.name_zh_tw}', name_zh_tw='{t.name_en}'")
                if not dry_run:
                    temp = t.name_en
                    t.name_en = t.name_zh_tw
                    t.name_zh_tw = temp
                    fixed += 1
            else:
                # Both have Chinese? Just clear name_en
                logger.info(f"  → FIX: Clear name_en (Chinese in both), mark as pending")
                if not dry_run:
                    t.name_en = None
                    t.translation_status = "pending"
                    fixed += 1
    
    return fixed


def find_english_names_to_clean(session) -> List[StockTranslation]:
    """
    Find entries where name_en contains legal suffixes or has incorrect casing.
    """
    all_translations = session.query(StockTranslation).filter(
        StockTranslation.name_en.isnot(None),
        StockTranslation.name_en != ""
    ).all()
    
    needs_cleaning = []
    for t in all_translations:
        if t.name_en:
            cleaned = clean_english_name(t.name_en)
            if cleaned != t.name_en:
                needs_cleaning.append(t)
    
    return needs_cleaning


def cleanup_english_names(session, entries: List[StockTranslation], dry_run: bool = True) -> int:
    """
    Clean up English stock names:
    1. Remove legal suffixes (Inc., Corp., Ltd., etc.)
    2. Normalize to title case
    """
    cleaned = 0
    
    for t in entries:
        old_name = t.name_en
        new_name = clean_english_name(old_name)
        
        if old_name != new_name:
            logger.info(f"  [{t.ticker}] '{old_name}' → '{new_name}'")
            if not dry_run:
                t.name_en = new_name
                cleaned += 1
    
    return cleaned


def generate_report(session):
    """Generate a data quality report."""
    total = session.query(func.count(StockTranslation.id)).scalar()
    
    # Count by status
    by_status = session.query(
        StockTranslation.translation_status,
        func.count(StockTranslation.id)
    ).group_by(StockTranslation.translation_status).all()
    
    # Count by market
    by_market = session.query(
        StockTranslation.market,
        func.count(StockTranslation.id)
    ).group_by(StockTranslation.market).all()
    
    # Missing translations
    missing_zh = session.query(func.count(StockTranslation.id)).filter(
        (StockTranslation.name_zh_tw.is_(None)) | (StockTranslation.name_zh_tw == "")
    ).scalar()
    
    missing_en = session.query(func.count(StockTranslation.id)).filter(
        (StockTranslation.name_en.is_(None)) | (StockTranslation.name_en == "")
    ).scalar()
    
    logger.info("\n" + "=" * 60)
    logger.info("TRANSLATION DATA QUALITY REPORT")
    logger.info("=" * 60)
    logger.info(f"Total entries: {total}")
    logger.info(f"\nBy Market:")
    for market, count in by_market:
        logger.info(f"  {market}: {count}")
    logger.info(f"\nBy Status:")
    for status, count in by_status:
        logger.info(f"  {status}: {count}")
    logger.info(f"\nMissing Data:")
    logger.info(f"  Missing Chinese name: {missing_zh}")
    logger.info(f"  Missing English name: {missing_en}")
    logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Cleanup and validate stock translations")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument("--report-only", action="store_true", help="Only generate report, no fixes")
    args = parser.parse_args()
    
    dry_run = args.dry_run
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No changes will be made")
    else:
        logger.info("⚠️  LIVE MODE - Changes will be applied")
    
    init_engine()
    create_all_tables()
    
    for session in get_session():
        # Generate report first
        generate_report(session)
        
        if args.report_only:
            break
        
        # Find issues
        logger.info("\n📋 ISSUE DETECTION")
        logger.info("-" * 40)
        
        # 1. Find duplicates
        duplicates = find_duplicates(session)
        logger.info(f"\n🔄 Found {len(duplicates)} tickers with multiple entries")
        
        # 2. Find misplaced Chinese
        misplaced = find_misplaced_chinese(session)
        logger.info(f"🔤 Found {len(misplaced)} entries with Chinese in name_en column")
        
        # 3. Find missing English names
        missing_en = find_missing_english_names(session)
        logger.info(f"📝 Found {len(missing_en)} entries missing English name")
        
        # 4. Find English names needing cleanup
        en_to_clean = find_english_names_to_clean(session)
        logger.info(f"🧹 Found {len(en_to_clean)} English names needing cleanup (legal suffixes/casing)")
        
        # Apply fixes
        if duplicates or misplaced or en_to_clean:
            logger.info("\n🔧 APPLYING FIXES")
            logger.info("-" * 40)
            
            deleted = cleanup_duplicates(session, duplicates, dry_run)
            fixed = fix_misplaced_chinese(session, misplaced, dry_run)
            
            # Clean English names
            if en_to_clean:
                logger.info(f"\n🧹 CLEANING ENGLISH NAMES:")
                cleaned_en = cleanup_english_names(session, en_to_clean, dry_run)
            else:
                cleaned_en = 0
            
            if not dry_run:
                session.commit()
                logger.info(f"\n✅ CHANGES APPLIED:")
                logger.info(f"   Deleted {deleted} duplicate entries")
                logger.info(f"   Fixed {fixed} misplaced Chinese entries")
                logger.info(f"   Cleaned {cleaned_en} English names")
            else:
                logger.info(f"\n📌 WOULD APPLY:")
                logger.info(f"   Delete {len([e for d in duplicates for e in d[1][1:]])} duplicate entries")
                logger.info(f"   Fix {len(misplaced)} misplaced Chinese entries")
                logger.info(f"   Clean {len(en_to_clean)} English names")
        else:
            logger.info("\n✅ No issues found - data looks clean!")
        
        break  # Only need one session
    
    logger.info("\n🏁 Done!")


if __name__ == "__main__":
    main()
