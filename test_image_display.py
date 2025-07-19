#!/usr/bin/env python3

"""
Quick test to verify image display functionality is working.
Run this script to test the unified display system.
"""

import os
import sys
from inkyremote import display_image_on_eink

def test_image_display():
    """Test image display functionality."""
    
    print("🧪 Testing image display functionality...")
    
    # Look for any image files to test with
    test_dirs = ['static/uploads', 'static', '.']
    test_image = None
    
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            for file in os.listdir(test_dir):
                if file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    test_image = os.path.join(test_dir, file)
                    break
        if test_image:
            break
    
    if not test_image:
        print("❌ No test image found. Please upload an image first.")
        return False
    
    print(f"📸 Testing with image: {test_image}")
    
    try:
        # Test the display function
        success, message = display_image_on_eink(test_image, saturation=0.5)
        
        if success:
            print(f"✅ Image display test PASSED: {message}")
            return True
        else:
            print(f"❌ Image display test FAILED: {message}")
            return False
            
    except Exception as e:
        print(f"💥 Image display test ERROR: {e}")
        return False

if __name__ == "__main__":
    print("=== InkyRemote Image Display Test ===")
    print()
    
    if test_image_display():
        print()
        print("🎉 Image display is working!")
        print("💡 Try uploading an image via the web UI and clicking Display")
    else:
        print()
        print("😞 Image display test failed")
        print("🔍 Check the logs: sudo journalctl -u inkyremote -f") 