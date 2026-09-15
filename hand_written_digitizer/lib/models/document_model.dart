class SegmentedRegionModel {
  final int id;
  final int historyId;
  final String regionType; // 'text' or 'diagram'
  final String imageUrl;
  final int x;
  final int y;
  final int width;
  final int height;

  SegmentedRegionModel({
    required this.id,
    required this.historyId,
    required this.regionType,
    required this.imageUrl,
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  factory SegmentedRegionModel.fromJson(Map<String, dynamic> json) {
    return SegmentedRegionModel(
      id: json['id'] as int,
      historyId: json['history_id'] as int,
      regionType: json['region_type'] as String,
      imageUrl: json['image_url'] as String,
      x: json['x'] as int,
      y: json['y'] as int,
      width: json['width'] as int,
      height: json['height'] as int,
    );
  }
}

class DocumentModel {
  final String id;
  final String title;
  final String date;
  final int pages;
  final String status; // 'Processed', 'Processing', 'Failed'
  final String? extractedText;
  final String? summary;
  final String? accuracy;
  final Map<String, String>? keyPoints;
  final String? originalImageUrl;
  final String? overlayImageUrl;
  final List<SegmentedRegionModel>? segmentedRegions;

  DocumentModel({
    required this.id,
    required this.title,
    required this.date,
    required this.pages,
    required this.status,
    this.extractedText,
    this.summary,
    this.accuracy,
    this.keyPoints,
    this.originalImageUrl,
    this.overlayImageUrl,
    this.segmentedRegions,
  });
}
