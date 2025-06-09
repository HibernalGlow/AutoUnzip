from loguru import logger
try:
    # 确保PageZ模块可以被导入
    from pagez.core.api import detect_archive_codepage
    PAGEZ_AVAILABLE = True
    logger.info("[green]PageZ模块导入成功[/green]")
except Exception as e:
    logger.info(f"[yellow]警告: 无法导入PageZ模块: {str(e)}，将使用默认代码页[/yellow]")
    PAGEZ_AVAILABLE = False
    