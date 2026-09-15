import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../viewmodels/scan_viewmodel.dart';

class ProcessingView extends ConsumerStatefulWidget {
  const ProcessingView({Key? key}) : super(key: key);

  @override
  ConsumerState<ProcessingView> createState() => _ProcessingViewState();
}

class _ProcessingViewState extends ConsumerState<ProcessingView> {
  @override
  void initState() {
    super.initState();
    // Start the actual image upload and OCR processing chain
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(scanViewModelProvider).startUploadProcessing((success) {
        if (mounted) {
          if (success) {
            final doc = ref.read(scanViewModelProvider).uploadedDocument;
            context.go('/complete', extra: doc);
          } else {
            final error = ref.read(scanViewModelProvider).errorMessage;
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text(error ?? 'Processing failed'),
                backgroundColor: Colors.redAccent,
              ),
            );
            context.pop();
          }
        }
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    final scanVM = ref.watch(scanViewModelProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF1F5F9), // Light background
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  minHeight: constraints.maxHeight,
                ),
                child: IntrinsicHeight(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 32.0),
                    child: Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 600),
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            const SizedBox(height: 16),
                            // App logo / category
                            Text(
                              'Digital Calm',
                              style: GoogleFonts.outfit(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                                color: const Color(0xFF64748B),
                                letterSpacing: 1.2,
                              ),
                            ),
                            const SizedBox(height: 24),
                            
                            // Sparkle Progress Circle
                            Center(
                              child: SizedBox(
                                height: 140,
                                width: 140,
                                child: Stack(
                                  alignment: Alignment.center,
                                  children: [
                                    // Progress track
                                    SizedBox(
                                      height: 120,
                                      width: 120,
                                      child: CircularProgressIndicator(
                                        value: scanVM.ocrProgress,
                                        strokeWidth: 8,
                                        backgroundColor: const Color(0xFFE2E8F0),
                                        valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF2563EB)),
                                      ),
                                    ),
                                    // Inner circle with sparkles
                                    Container(
                                      height: 90,
                                      width: 90,
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFEFF6FF),
                                        shape: BoxShape.circle,
                                      ),
                                      child: const Center(
                                        child: Icon(
                                          Icons.auto_awesome, // Sparkles
                                          color: Color(0xFF2563EB),
                                          size: 36,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            const SizedBox(height: 36),
                            
                            // AI Reading Text
                            Text(
                              'Our AI is reading your\nhandwriting...',
                              textAlign: TextAlign.center,
                              style: GoogleFonts.outfit(
                                fontSize: 22,
                                fontWeight: FontWeight.bold,
                                color: const Color(0xFF0F172A),
                                height: 1.3,
                              ),
                            ),
                            const SizedBox(height: 12),
                            Text(
                              'Transforming your physical notes into\nstructured digital intelligence.',
                              textAlign: TextAlign.center,
                              style: GoogleFonts.inter(
                                fontSize: 14,
                                color: const Color(0xFF64748B),
                                height: 1.4,
                              ),
                            ),
                            const SizedBox(height: 40),
                            
                            // Processing Steps Container
                            Container(
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(20),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withOpacity(0.02),
                                    blurRadius: 10,
                                    offset: const Offset(0, 4),
                                  ),
                                ],
                              ),
                              padding: const EdgeInsets.all(20),
                              child: Column(
                                children: [
                                  _buildStepRow(
                                    icon: Icons.document_scanner_outlined,
                                    title: 'OCR Progress',
                                    subtitle: scanVM.ocrStatusText,
                                    trailing: SizedBox(
                                      width: 80,
                                      child: LinearProgressIndicator(
                                        value: scanVM.ocrProgress,
                                        backgroundColor: const Color(0xFFE2E8F0),
                                        valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF2563EB)),
                                      ),
                                    ),
                                    isActive: true,
                                  ),
                                  const Divider(height: 24, color: Color(0xFFF1F5F9)),
                                  _buildStepRow(
                                    icon: Icons.format_quote_rounded,
                                    title: 'Text Extraction',
                                    subtitle: scanVM.extractionStatus,
                                    trailing: Icon(
                                      scanVM.extractionStatus.contains('successfully') 
                                          ? Icons.check_circle_rounded 
                                          : Icons.hourglass_empty_rounded,
                                      color: scanVM.extractionStatus.contains('successfully') 
                                          ? const Color(0xFF10B981) 
                                          : const Color(0xFF94A3B8),
                                      size: 20,
                                    ),
                                    isActive: scanVM.ocrProgress >= 0.8,
                                  ),
                                  const Divider(height: 24, color: Color(0xFFF1F5F9)),
                                  _buildStepRow(
                                    icon: Icons.summarize_outlined,
                                    title: 'Summary Generation',
                                    subtitle: scanVM.summaryStatus,
                                    trailing: Icon(
                                      scanVM.summaryStatus.contains('ready')
                                          ? Icons.check_circle_rounded
                                          : Icons.more_horiz_rounded,
                                      color: scanVM.summaryStatus.contains('ready')
                                          ? const Color(0xFF10B981)
                                          : const Color(0xFF94A3B8),
                                      size: 20,
                                    ),
                                    isActive: scanVM.extractionStatus.contains('successfully'),
                                  ),
                                  const Divider(height: 24, color: Color(0xFFF1F5F9)),
                                  _buildStepRow(
                                    icon: Icons.task_alt_rounded,
                                    title: 'Document Creation',
                                    subtitle: scanVM.documentStatus,
                                    trailing: Icon(
                                      scanVM.documentStatus == 'Completed'
                                          ? Icons.check_circle_rounded
                                          : Icons.radio_button_off_rounded,
                                      color: scanVM.documentStatus == 'Completed'
                                          ? const Color(0xFF10B981)
                                          : const Color(0xFF94A3B8),
                                      size: 20,
                                    ),
                                    isActive: scanVM.summaryStatus.contains('ready'),
                                  ),
                                ],
                              ),
                            ),
                            const Spacer(),
                            
                            // Cancel Button
                            TextButton(
                              onPressed: () {
                                scanVM.cancelProcessing();
                                context.pop();
                              },
                              child: Text(
                                'Cancel Processing',
                                style: GoogleFonts.inter(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w600,
                                  color: const Color(0xFF475569),
                                ),
                              ),
                            ),
                            const SizedBox(height: 16),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          }
        ),
      ),
    );
  }

  Widget _buildStepRow({
    required IconData icon,
    required String title,
    required String subtitle,
    required Widget trailing,
    required bool isActive,
  }) {
    return Opacity(
      opacity: isActive ? 1.0 : 0.4,
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFFF1F5F9),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: const Color(0xFF475569), size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: GoogleFonts.inter(
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    color: const Color(0xFF0F172A),
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: GoogleFonts.inter(
                    fontSize: 12,
                    color: const Color(0xFF64748B),
                  ),
                ),
              ],
            ),
          ),
          trailing,
        ],
      ),
    );
  }
}
