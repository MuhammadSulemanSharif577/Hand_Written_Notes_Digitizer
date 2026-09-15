import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import '../services/api_service.dart';
import '../models/document_model.dart';

class ScanViewModel extends ChangeNotifier {
  bool _isFlashOn = false;
  bool _isGridOn = false;

  // Processing States
  double _ocrProgress = 0.0;
  String _ocrStatusText = 'Analyzing ink strokes';
  String _extractionStatus = 'Waiting...';
  String _summaryStatus = 'Pending';
  String _documentStatus = 'Queued';

  bool _isProcessing = false;
  File? _selectedImage;
  String? _errorMessage;
  DocumentModel? _uploadedDocument;

  bool get isFlashOn => _isFlashOn;
  bool get isGridOn => _isGridOn;

  double get ocrProgress => _ocrProgress;
  String get ocrStatusText => _ocrStatusText;
  String get extractionStatus => _extractionStatus;
  String get summaryStatus => _summaryStatus;
  String get documentStatus => _documentStatus;
  bool get isProcessing => _isProcessing;
  File? get selectedImage => _selectedImage;
  String? get errorMessage => _errorMessage;
  DocumentModel? get uploadedDocument => _uploadedDocument;

  void toggleFlash() {
    _isFlashOn = !_isFlashOn;
    notifyListeners();
  }

  void toggleGrid() {
    _isGridOn = !_isGridOn;
    notifyListeners();
  }

  final ImagePicker _picker = ImagePicker();

  Future<bool> selectImage(ImageSource source) async {
    _errorMessage = null;
    _uploadedDocument = null;
    try {
      final pickedFile = await _picker.pickImage(
        source: source,
        imageQuality: 85,
        maxWidth: 2000,
        maxHeight: 2000,
      );
      if (pickedFile != null) {
        _selectedImage = File(pickedFile.path);
        notifyListeners();
        return true;
      }
    } catch (e) {
      _errorMessage = 'Failed to select image: $e';
      notifyListeners();
    }
    return false;
  }

  Future<void> startUploadProcessing(Function(bool success) onComplete) async {
    if (_selectedImage == null) {
      _errorMessage = 'No image selected';
      notifyListeners();
      return;
    }

    _isProcessing = true;
    _ocrProgress = 0.1;
    _ocrStatusText = 'Preparing image... (10%)';
    _extractionStatus = 'Waiting...';
    _summaryStatus = 'Pending';
    _documentStatus = 'Queued';
    _errorMessage = null;
    notifyListeners();

    // Phase 1: Simulate image preparation
    await Future.delayed(const Duration(milliseconds: 500));
    _ocrProgress = 0.3;
    _ocrStatusText = 'Uploading image to Cloudinary... (30%)';
    notifyListeners();

    // Phase 2: Call backend API to upload to Cloudinary and database
    final response = await ApiService.uploadImage(_selectedImage!);

    if (response['success'] == true) {
      _ocrProgress = 0.7;
      _ocrStatusText = 'Running OCR on note... (70%)';
      _extractionStatus = 'Extracting handwriting text...';
      notifyListeners();

      await Future.delayed(const Duration(milliseconds: 500));
      _ocrProgress = 0.9;
      _ocrStatusText = 'Saving to database... (90%)';
      _extractionStatus = 'Text extracted successfully';
      _summaryStatus = 'Generating summary and key points...';
      notifyListeners();

      await Future.delayed(const Duration(milliseconds: 500));
      _ocrProgress = 1.0;
      _ocrStatusText = 'Completed!';
      _summaryStatus = 'Summary ready';
      _documentStatus = 'Completed';

      final item = response['data'];
      final id = item['id'].toString();
      final uploadTime = DateTime.parse(item['upload_time']);
      final dateStr =
          "${_getMonthAbbreviation(uploadTime.month)} ${uploadTime.day}, ${uploadTime.year}";

      final rawRegions = item['segmented_regions'] as List<dynamic>?;
      final regionsList = rawRegions != null
          ? rawRegions
                .map(
                  (r) =>
                      SegmentedRegionModel.fromJson(r as Map<String, dynamic>),
                )
                .toList()
          : <SegmentedRegionModel>[];

      _uploadedDocument = DocumentModel(
        id: id,
        title: 'Digitized Note #$id',
        date: dateStr,
        pages: 1,
        status: 'Processed',
        // The backend does not return calibrated document-level confidence.
        // Do not present a fabricated OCR percentage to the user.
        accuracy: null,
        extractedText: item['extracted_text'],
        summary: item['summary'],
        originalImageUrl: item['image_url'],
        overlayImageUrl: item['overlay_image_url'],
        segmentedRegions: regionsList,
        keyPoints: {
          'Upload Time': uploadTime.toLocal().toString().split('.')[0],
          'Storage': 'Cloudinary',
        },
      );

      _isProcessing = false;
      notifyListeners();
      onComplete(true);
    } else {
      _isProcessing = false;
      _errorMessage = response['error'] ?? 'Image upload and processing failed';
      _ocrStatusText = 'Failed';
      _extractionStatus = 'Failed';
      _summaryStatus = 'Failed';
      _documentStatus = 'Failed';
      notifyListeners();
      onComplete(false);
    }
  }

  String _getMonthAbbreviation(int month) {
    const months = [
      'Jan',
      'Feb',
      'Mar',
      'Apr',
      'May',
      'Jun',
      'Jul',
      'Aug',
      'Sep',
      'Oct',
      'Nov',
      'Dec',
    ];
    if (month >= 1 && month <= 12) {
      return months[month - 1];
    }
    return '';
  }

  void cancelProcessing() {
    _isProcessing = false;
    _ocrProgress = 0.0;
    notifyListeners();
  }
}

final scanViewModelProvider = ChangeNotifierProvider<ScanViewModel>((ref) {
  return ScanViewModel();
});
