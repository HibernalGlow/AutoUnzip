"""测试 ZIP 编码读取"""
import zipfile

zip_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)\2019 [Nameless (鬼針草)].zip'

print("测试不同编码方式读取 ZIP...")

# 测试的路径（从 list_files_in_zip 获取的）
test_path = '2019/04/[2019-04-26] 毎月のR18同人プラン2019.4/0.avif'

for encoding in ['utf-8', 'gbk', 'cp437', 'shift_jis', None]:
    print(f"\n尝试编码: {encoding}")
    try:
        with zipfile.ZipFile(zip_path, 'r', metadata_encoding=encoding) as zf:
            # 列出文件名
            names = zf.namelist()
            print(f"  文件数: {len(names)}")
            
            # 查找包含 0.avif 的文件
            avif_files = [n for n in names if '0.avif' in n]
            if avif_files:
                print(f"  找到 {len(avif_files)} 个 avif 文件")
                first_avif = avif_files[0]
                print(f"  第一个: {repr(first_avif)}")
                
                # 尝试读取
                try:
                    data = zf.read(first_avif)
                    print(f"  ✓ 成功读取 {len(data)} 字节")
                    
                    # 测试是否能用我们的路径读取
                    if first_avif == test_path:
                        print(f"  ✓ 路径匹配！")
                    else:
                        print(f"  ✗ 路径不匹配")
                        print(f"    期望: {repr(test_path)}")
                        print(f"    实际: {repr(first_avif)}")
                    break
                except Exception as e:
                    print(f"  ✗ 读取失败: {e}")
    except Exception as e:
        print(f"  ✗ 打开失败: {e}")
