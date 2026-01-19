"""直接测试 ZIP 读取"""
import zipfile

zip_path = r'E:\1Hub\EH\1EHV\[Nameless (鬼針草)]\3. 画集\PIXIV FANBOX 作品集 (2025.11.12)\2019 [Nameless (鬼針草)].zip'
file_path = '2019/04/[2019-04-26] 毎月のR18同人プラン2019.4/0.avif'

print(f"ZIP 文件: {zip_path}")
print(f"目标文件: {file_path}")
print()

try:
    with zipfile.ZipFile(zip_path, 'r') as zf:
        print("ZIP 文件打开成功")
        
        # 列出所有文件
        names = zf.namelist()
        print(f"ZIP 内文件数: {len(names)}")
        print("\n前 10 个文件:")
        for i, name in enumerate(names[:10]):
            print(f"  {i+1}. {repr(name)}")
        
        # 尝试读取目标文件
        print(f"\n尝试读取: {repr(file_path)}")
        try:
            data = zf.read(file_path)
            print(f"✓ 成功读取 {len(data)} 字节")
        except KeyError as e:
            print(f"✗ 文件不存在: {e}")
            
            # 尝试查找相似的文件名
            print("\n查找包含 '0.avif' 的文件:")
            for name in names:
                if '0.avif' in name:
                    print(f"  - {repr(name)}")
        
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
