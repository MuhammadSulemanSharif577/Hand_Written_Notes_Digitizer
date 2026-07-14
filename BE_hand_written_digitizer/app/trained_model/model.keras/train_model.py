import os
import argparse
import numpy as np
import matplotlib.pyplot as plt
import tensorflow as tf
from tensorflow.keras import layers, models

# Define paths dynamically by locating the project root
def find_project_root():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    while current_dir != os.path.dirname(current_dir):
        if os.path.isdir(os.path.join(current_dir, "dataset")):
            return current_dir
        current_dir = os.path.dirname(current_dir)
    return os.path.dirname(os.path.abspath(__file__))

PROJECT_ROOT = find_project_root()
DATASET_PATH = os.path.join(PROJECT_ROOT, "dataset", "processed", "byclass_dataset.npz")
MODEL_DIR = os.path.join(PROJECT_ROOT, "app", "trained_model")
MODEL_PATH = os.path.join(MODEL_DIR, "ocr_model.keras")
PLOT_PATH = os.path.join(MODEL_DIR, "training_performance.png")

def main():
    parser = argparse.ArgumentParser(description="Train EMNIST Digits and Characters CNN Classifier")
    parser.add_argument("--subset-size", type=int, default=300000, help="Number of training samples to use (-1 for all)")
    parser.add_argument("--epochs", type=int, default=12, help="Number of epochs to train")
    parser.add_argument("--batch-size", type=int, default=128, help="Batch size for training")
    args = parser.parse_args()

    # Ensure output directory exists
    # If a model.keras directory already exists, delete it first to avoid collision
    if os.path.exists(MODEL_PATH):
        if os.path.isdir(MODEL_PATH):
            import shutil
            shutil.rmtree(MODEL_PATH)
        else:
            os.remove(MODEL_PATH)
    os.makedirs(MODEL_DIR, exist_ok=True)

    print("==========================================")
    print("Loading pre-processed EMNIST dataset...")
    print("==========================================")
    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"NumPy dataset archive not found at {DATASET_PATH}. Please run conversion script first.")

    dataset = np.load(DATASET_PATH)
    x_train_full = dataset["x_train"]
    y_train_full = dataset["y_train"]
    x_test_full = dataset["x_test"]
    y_test_full = dataset["y_test"]

    print(f"Full Train shape: {x_train_full.shape}")
    print(f"Full Test shape:  {x_test_full.shape}")

    # Determine subset sizing
    num_train = len(x_train_full)
    num_test = len(x_test_full)
    
    if 0 < args.subset_size < num_train:
        print(f"Sampling training subset of size: {args.subset_size}...")
        # Get reproducible random indices
        np.random.seed(42)
        train_indices = np.random.choice(num_train, args.subset_size, replace=False)
        x_train = x_train_full[train_indices]
        y_train = y_train_full[train_indices]
        
        # Sample test subset proportionally (approx 15% of train size)
        test_subset_size = int(args.subset_size * 0.15)
        test_subset_size = min(test_subset_size, num_test)
        print(f"Sampling testing subset of size: {test_subset_size}...")
        test_indices = np.random.choice(num_test, test_subset_size, replace=False)
        x_test = x_test_full[test_indices]
        y_test = y_test_full[test_indices]
    else:
        print("Training on full dataset...")
        x_train = x_train_full
        y_train = y_train_full
        x_test = x_test_full
        y_test = y_test_full

    # Reshape and normalize images
    print("Normalizing and reshaping images...")
    x_train = x_train.reshape(-1, 28, 28, 1).astype(np.float32) / 255.0
    x_test = x_test.reshape(-1, 28, 28, 1).astype(np.float32) / 255.0

    print(f"Subset Train images shape: {x_train.shape}")
    print(f"Subset Test images shape:  {x_test.shape}")

    # Build CNN Architecture
    print("Building CNN Model Architecture...")
    model = models.Sequential([
        layers.Input(shape=(28, 28, 1)),
        
        layers.Conv2D(32, (3, 3), activation='relu', padding='same'),
        layers.Conv2D(32, (3, 3), activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.25),
        
        layers.Conv2D(64, (3, 3), activation='relu', padding='same'),
        layers.Conv2D(64, (3, 3), activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D((2, 2)),
        layers.Dropout(0.25),
        
        layers.Flatten(),
        layers.Dense(256, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.5),
        layers.Dense(62, activation='softmax')
    ])

    model.compile(
        optimizer='adam',
        loss='sparse_categorical_crossentropy',
        metrics=['accuracy']
    )
    
    model.summary()

    print("\n==========================================")
    print(f"Training CNN Model for {args.epochs} epochs...")
    print("==========================================")
    
    history = model.fit(
        x_train, y_train,
        epochs=args.epochs,
        batch_size=args.batch_size,
        validation_data=(x_test, y_test),
        verbose=1
    )

    # Evaluate model
    print("\nEvaluating model on test split...")
    test_loss, test_acc = model.evaluate(x_test, y_test, verbose=0)
    print(f"[+] Test Accuracy: {test_acc:.4f}")
    print(f"[+] Test Loss:     {test_loss:.4f}")

    # Save trained model
    print(f"Saving model to {MODEL_PATH}...")
    model.save(MODEL_PATH)

    # Plot and save metrics history
    print(f"Generating training performance plot at {PLOT_PATH}...")
    plt.figure(figsize=(12, 5))

    # Accuracy Plot
    plt.subplot(1, 2, 1)
    plt.plot(history.history['accuracy'], label='Train Accuracy', color='#1f77b4', linewidth=2)
    plt.plot(history.history['val_accuracy'], label='Val Accuracy', color='#ff7f0e', linewidth=2)
    plt.title('Training & Validation Accuracy')
    plt.xlabel('Epoch')
    plt.ylabel('Accuracy')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(loc='lower right')

    # Loss Plot
    plt.subplot(1, 2, 2)
    plt.plot(history.history['loss'], label='Train Loss', color='#d62728', linewidth=2)
    plt.plot(history.history['val_loss'], label='Val Loss', color='#2ca02c', linewidth=2)
    plt.title('Training & Validation Loss')
    plt.xlabel('Epoch')
    plt.ylabel('Loss')
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(PLOT_PATH, dpi=150)
    plt.close()

    print("Model training execution completed successfully!")

if __name__ == "__main__":
    main()
