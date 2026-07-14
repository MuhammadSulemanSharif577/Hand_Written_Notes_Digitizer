import cloudinary

cloudinary.config(
    cloud_name="dgwvj6d9f",
    api_key="319747968129495",
    api_secret="nEZmKxqHZtgl54nS16ElUUakUpQ",
    secure=True
)

import cloudinary.uploader

if __name__ == "__main__":
    result = cloudinary.uploader.upload("images/IMG-20250611-WA0018.jpg")
    print(result["secure_url"])