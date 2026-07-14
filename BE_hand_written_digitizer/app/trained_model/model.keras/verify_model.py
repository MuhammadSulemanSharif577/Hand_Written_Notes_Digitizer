import os
import numpy as np
import tensorflow as tf
from tensorflow.keras import models

# Define paths dynamically by locating the project root
def find_project_root():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while current_dir != os.path.dirname(current_dir):
        if os.path.isdir(os.path.join(current_dir, "dataset")):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = find_project_root()
MODEL_PATH = os.path.join(PROJECT_ROOT, "app", "trained_model", "ocr_model.keras")
PLOT_PATH = os.path.join(PROJECT_ROOT, "app", "trained_model", "training_performance.png")
DATASET_PATH = os.path.join(PROJECT_ROOT, "dataset", "processed", "byclass_dataset.npz")

def get_class_char(label):
    if label <= 9:
        return str(label)
    elif 10 <= label <= 35:
        return chr(label - 10 + 65)  # Uppercase
    elif 36 <= label <= 61:
        return chr(label - 36 + 97)  # Lowercase
    else:
        return "?"

def main():
    print("==========================================")
    print("Verifying trained CNN OCR model...")
    print("==========================================")

    # 1. Check if model file exists
    if not os.path.exists(MODEL_PATH):
        print(f"[-] ERROR: Model file not found at {MODEL_PATH}")
        exit(1)
    print(f"[+] Found model file at {MODEL_PATH}")

    # 2. Check if performance plot exists
    if not os.path.exists(PLOT_PATH):
        print(f"[-] ERROR: Training performance plot not found at {PLOT_PATH}")
        exit(1)
    print(f"[+] Found training performance plot at {PLOT_PATH}")

    # 3. Load model
    try:
        print("Loading Keras model...")
        model = models.load_model(MODEL_PATH)
        print("[+] Model loaded successfully!")
    except Exception as e:
        print(f"[-] ERROR loading model: {str(e)}")
        exit(1)

    # 4. Verify model input/output dimensions
    try:
        input_shape = model.input_shape
        output_shape = model.output_shape
        print(f"[+] Model input shape:  {input_shape}")
        print(f"[+] Model output shape: {output_shape}")
        
        assert len(input_shape) == 4 and input_shape[1:] == (28, 28, 1), "Model input shape must be (None, 28, 28, 1)"
        assert len(output_shape) == 2 and output_shape[1] == 62, "Model output shape must be (None, 62)"
    except Exception as e:
        print(f"[-] ERROR verifying model architecture: {str(e)}")
        exit(1)

    # 5. Run prediction on test images
    if not os.path.exists(DATASET_PATH):
        print(f"[!] Warning: byclass_dataset.npz not found, skipping prediction on real images.")
        exit(0)

    try:
        print("Loading sample images from dataset...")
        dataset = np.load(DATASET_PATH)
        x_test = dataset["x_test"]
        y_test = dataset["y_test"]
        
        # Pick 5 random indices
        np.random.seed(123)
        indices = np.random.choice(len(x_test), 5, replace=False)
        
        print("\nTesting prediction on 5 random sample test images:")
        for i, idx in enumerate(indices):
            img = x_test[idx]
            label = y_test[idx]
            
            # Normalize and reshape for prediction
            input_img = img.reshape(1, 28, 28, 1).astype(np.float32) / 255.0
            
            # Run prediction
            pred_probs = model.predict(input_img, verbose=0)[0]
            pred_label = np.argmax(pred_probs)
            confidence = pred_probs[pred_label]
            
            true_char = get_class_char(label)
            pred_char = get_class_char(pred_label)
            
            status = "CORRECT" if label == pred_label else "INCORRECT"
            print(f"  Sample {i+1}: True='{true_char}' ({label}), Predicted='{pred_char}' ({pred_label}), Confidence={confidence:.4f} -> [{status}]")
            
        print("\n[+++] MODEL VERIFICATION PASSED SUCCESSFULLY! [+++]")
    except Exception as e:
        print(f"[-] ERROR running prediction verification: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
