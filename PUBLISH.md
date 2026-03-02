# Publish Guide

## 1. Init and push to GitHub

```bash
cd wechat-plugin
git init
git add .
git commit -m "feat: initial openclaw wechat plugin"
git branch -M main
git remote add origin https://github.com/RolandXD/openclaw-wechat-plugin.git
git push -u origin main
```

If first push needs auth, use GitHub PAT.

## 2. Install from GitHub

```bash
pip install "git+https://github.com/RolandXD/openclaw-wechat-plugin.git@main"
openclaw-wechat-plugin
```

## 3. Publish to PyPI (optional)

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```

Then users install with:

```bash
pip install openclaw-wechat-plugin
```
