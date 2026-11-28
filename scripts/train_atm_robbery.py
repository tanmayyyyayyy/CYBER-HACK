"""Fine-tune YOLOv8n on the Simuletic ATM robbery dataset."""

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATASET = "simuletic/cctv-atm-robbery-detection-dataset-gun-and-knife"
EXPECTED_CLASSES = {"offender", "victim", "gun", "knife"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Use a local YOLO dataset YAML instead of Kaggle.")
    parser.add_argument("--device", default="0", help="CUDA device index, or cpu.")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--publish", action="store_true", help="Copy best.pt into models/atm_robbery.pt.")
    args = parser.parse_args()
    destination = ROOT / "models" / "atm_robbery.pt"
    if args.publish and destination.exists():
        parser.error(f"Move the existing checkpoint before publishing: {destination}")

    import yaml
    from ultralytics import YOLO

    if args.data is None:
        import kagglehub

        downloaded = Path(kagglehub.dataset_download(DATASET))
        candidates = sorted(path for path in downloaded.rglob("data.y*ml") if path.suffix in {".yaml", ".yml"})
        if len(candidates) != 1:
            parser.error(f"Expected one data.yaml under {downloaded}. Pass --data with the dataset YAML.")
        args.data = candidates[0]

    data_path = args.data.resolve()
    config = yaml.safe_load(data_path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        parser.error("Dataset YAML must contain a mapping.")
    names = config.get("names", [])
    labels = names.values() if isinstance(names, dict) else names
    if {str(label).strip().lower() for label in labels} != EXPECTED_CLASSES or len(names) != 4:
        parser.error("Dataset YAML must define offender, victim, gun and knife classes.")
    if not config.get("train") or not config.get("val"):
        parser.error("Dataset YAML must define training and validation splits.")

    local_weights = ROOT / "models" / "yolov8n.pt"
    model = YOLO(str(local_weights) if local_weights.is_file() else "yolov8n.pt")
    model.train(
        data=str(data_path), epochs=args.epochs, batch=args.batch, imgsz=640,
        device=args.device, workers=0, seed=42,
        project=str(ROOT / "models" / "training"), name="atm_robbery",
    )
    checkpoint = Path(model.trainer.best)
    if not checkpoint.is_file():
        raise RuntimeError(f"Training did not produce a checkpoint at {checkpoint}")
    print(f"Best checkpoint: {checkpoint}")
    if args.publish:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with checkpoint.open("rb") as source, destination.open("xb") as target:
            shutil.copyfileobj(source, target)
        print(f"Live detector checkpoint: {destination}")


if __name__ == "__main__":
    main()
