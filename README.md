# Image Downloader

通用网页图片下载器，支持多种琴谱网站。输入网址后列出所有图片（文件名 + 大小），按条件筛选下载，自动转为 JPG。

## 功能

- **智能发现** — 五层扫描引擎：DOM 解析 → RAW 文本 → SSR 数据 → iframe → 外部 CSS
- **自动反封锁** — Cookie 持久化、UA 轮换、Referer 伪造、防盗链绕过
- **灵活筛选** — 序号、范围（2-6）、大小条件（>100KB）、组合筛选
- **自动转 JPG** — PNG/WebP/GIF/BMP → JPG，SVG 自动跳过
- **直接图片链接** — 输入 `.jpg` 链接直接下载

## 安装

```bash
pip install -r requirements.txt
```

## 用法

```bash
python image_downloader.py                              # 交互模式
python image_downloader.py <url>                        # 交互 + 预填 URL
python image_downloader.py <url> --select "2-5,>100KB"  # 自动下载
python image_downloader.py <url> --deep                 # 全层扫描
python image_downloader.py <url> --no-convert           # 保留原格式
```

## 截图

运行 `python image_downloader.py` 后输入网址，会列出所有图片：

```
=====================================================================================
   #        Size   Sts  Source              Filename
=====================================================================================
   1     20.6 KB    OK  img                 logo.png
   2    308.1 KB    OK  img                 562412ad3e0d0fde-2.jpg
   3    301.4 KB    OK  img                 562412ad3e0d0fde-3.jpg
  ...
=====================================================================================
```

然后通过筛选条件选择要下载的图片：

```
[?] number | 1,3,7 | 2-6 | >100KB | <1MB | >=500KB | all | q
> 2-4
```

## 已验证站点

- qinpuwang.com（琴谱网）
- jitashe.net（吉他社）
- jtp123.com（吉他谱123）
- 本人是个吉他手，平时需要下载一些免费的吉他谱，所以写了这个项目，只用于提供免费的曲谱网站使用且测试学习用，避免白嫖收费的曲谱，尊重知识产权和别人的劳动。

## 依赖

- Python 3.8+
- requests
- beautifulsoup4
- Pillow
