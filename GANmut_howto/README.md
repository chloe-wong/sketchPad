# SketchPad

GANmut: Uses an expressive and interpretable conditional space of emotions to manipulate facial expressions.

---

### 1. Where to put these files 
In models, download GANmut repo. Add model.py, manifest.json and requirements.txt into the GANmut folder. Add my_ganmut.py to utils folder of GANmut folder.

```
sketchpad/
├── models/
│   ├── _template/
│   └── GANmut/  ← The repo folder
│   │   └── manifest.json
│   │   └── model.py
│   │   └── requirements.txt
│   │   └──utils/
│   │   │   └──my_ganmut.py
...
```

### 2. Commands to run after adding
```bash
./scripts/setup_model.sh GANmut
./scripts/setup_backend.sh
./scripts/start.sh
```

Open **http://localhost:5173**