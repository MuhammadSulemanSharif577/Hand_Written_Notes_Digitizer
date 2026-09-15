import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/document_model.dart';
import '../services/api_service.dart';

class HomeViewModel extends ChangeNotifier {
  int _currentIndex = 0;
  List<DocumentModel> _recentDocuments = [];
  bool _isLoading = false;
  final Set<String> _deletingDocumentIds = <String>{};
  String _userName = '';
  String _userEmail = '';

  int get currentIndex => _currentIndex;
  List<DocumentModel> get recentDocuments => _recentDocuments;
  bool get isLoading => _isLoading;
  bool isDeletingDocument(String id) => _deletingDocumentIds.contains(id);
  String get userName => _userName;
  String get userEmail => _userEmail;

  HomeViewModel() {
    loadUserData();
    loadHistory();
  }

  void setIndex(int index) {
    _currentIndex = index;
    notifyListeners();
  }

  Future<void> loadUserData() async {
    final info = await ApiService.getUserInfo();
    _userName = info['name'] ?? 'User';
    _userEmail = info['email'] ?? '';
    notifyListeners();
  }

  // Statistics
  int get totalDocuments => _recentDocuments.length;
  int get totalSummaries => _recentDocuments
      .where((doc) => doc.summary?.trim().isNotEmpty == true)
      .length;
  int get monthlyDocuments => _recentDocuments.length;
  int get monthlyTarget => 10;
  double get targetProgress => monthlyTarget > 0
      ? (monthlyDocuments / monthlyTarget).clamp(0.0, 1.0)
      : 0.0;

  Future<void> loadHistory() async {
    _isLoading = true;
    notifyListeners();

    try {
      final records = await ApiService.fetchHistory();
      _recentDocuments = records.map((item) {
        final id = item['id'].toString();
        final uploadTime = DateTime.parse(item['upload_time']);
        final dateStr =
            "${_getMonthAbbreviation(uploadTime.month)} ${uploadTime.day}, ${uploadTime.year}";

        final rawRegions = item['segmented_regions'] as List<dynamic>?;
        final regionsList = rawRegions != null
            ? rawRegions
                  .map(
                    (r) => SegmentedRegionModel.fromJson(
                      r as Map<String, dynamic>,
                    ),
                  )
                  .toList()
            : <SegmentedRegionModel>[];

        return DocumentModel(
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
            'Location': 'Cloudinary + MySQL',
          },
        );
      }).toList();
    } catch (e) {
      debugPrint('Error loading history: $e');
    }

    _isLoading = false;
    notifyListeners();
  }

  Future<String?> deleteDocument(String id) async {
    if (_deletingDocumentIds.contains(id)) return null;
    _deletingDocumentIds.add(id);
    notifyListeners();

    try {
      final result = await ApiService.deleteDocument(id);
      if (result['success'] == true) {
        _recentDocuments.removeWhere((document) => document.id == id);
        return null;
      }
      return result['error']?.toString() ?? 'Could not delete document';
    } finally {
      _deletingDocumentIds.remove(id);
      notifyListeners();
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

  DocumentModel get cognitivePsychologyDocument => DocumentModel(
    id: 'cog_psych_1',
    title: 'Cognitive Psychology',
    date: 'Oct 25, 2023',
    pages: 1,
    status: 'Processed',
    accuracy: '98%',
    extractedText:
        'The human brain is not a static organ. Through neural plasticity, it reconfigures itself based on environmental stimuli...\n\nCognitive psychology explores how we process information. A key area of study is neural plasticity, which describes the brain\'s ability to change throughout an individual\'s life. This occurs through the strengthening or weakening of synapses.\n\nMemory consolidation is the process where a temporary, labile memory is transformed into a more stable, long-term memory.',
    summary:
        'Cognitive psychology examines how people process and retain information.\nNeural plasticity allows the brain to reorganize by changing synaptic connections.\nMemory consolidation transforms temporary memories into stable long-term memories.\nSleep supports consolidation and long-term retention.',
    keyPoints: {
      'Topic': 'Cognitive Psychology & Neurobiology',
      'Definition':
          'Neural plasticity is the brain\'s ability to reorganize itself by forming new connections.',
      'Importance':
          'Sleep is critical for memory consolidation and long-term retention.',
    },
    originalImageUrl:
        'https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&q=80&w=600',
  );
}

final homeViewModelProvider = ChangeNotifierProvider<HomeViewModel>((ref) {
  return HomeViewModel();
});
