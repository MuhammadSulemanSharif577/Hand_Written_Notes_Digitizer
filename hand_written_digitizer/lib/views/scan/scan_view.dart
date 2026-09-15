import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import '../../viewmodels/scan_viewmodel.dart';

class ScanView extends ConsumerWidget {
  const ScanView({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scanVM = ref.watch(scanViewModelProvider);

    return Scaffold(
      backgroundColor: const Color(0xFFF8FAFC),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Color(0xFF0F172A)),
          onPressed: () => context.pop(),
        ),
        title: Text(
          'Scan Notes',
          style: GoogleFonts.outfit(
            fontWeight: FontWeight.bold,
            fontSize: 20,
            color: const Color(0xFF0F172A),
          ),
        ),
        actions: [
          IconButton(
            icon: Icon(
              scanVM.isFlashOn ? Icons.flash_on_rounded : Icons.flash_off_rounded,
              color: scanVM.isFlashOn ? const Color(0xFFEAB308) : const Color(0xFF64748B),
            ),
            onPressed: scanVM.toggleFlash,
          ),
          IconButton(
            icon: Icon(
              scanVM.isGridOn ? Icons.grid_on_rounded : Icons.grid_off_rounded,
              color: scanVM.isGridOn ? const Color(0xFF2563EB) : const Color(0xFF64748B),
            ),
            onPressed: scanVM.toggleGrid,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: SafeArea(
        child: Center(
          child: Container(
            constraints: const BoxConstraints(maxWidth: 600),
            child: Column(
              children: [
                const SizedBox(height: 16),
                Text(
                  'Align your notes within the frame for best results.',
                  style: GoogleFonts.inter(
                    fontSize: 14,
                    color: const Color(0xFF64748B),
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                
                // Viewfinder camera viewport
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 24.0),
                    child: Container(
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: Colors.black.withOpacity(0.85),
                        borderRadius: BorderRadius.circular(28),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withOpacity(0.1),
                            blurRadius: 10,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(28),
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            // Mock Notebook Background
                            Image.network(
                              'https://images.unsplash.com/photo-1544816155-12df9643f363?auto=format&fit=crop&q=80&w=600', // Notebook on wood table
                              height: double.infinity,
                              width: double.infinity,
                              fit: BoxFit.cover,
                              color: Colors.black.withOpacity(0.55),
                              colorBlendMode: BlendMode.darken,
                              errorBuilder: (context, error, stackTrace) {
                                return Container(
                                  color: const Color(0xFF1E293B),
                                  child: const Center(
                                    child: Icon(Icons.menu_book, color: Colors.white24, size: 80),
                                  ),
                                );
                              },
                            ),
                            
                            // Crop/Align Guide Overlay Frame
                            Padding(
                              padding: const EdgeInsets.all(24.0),
                              child: Container(
                                decoration: BoxDecoration(
                                  border: Border.all(
                                    color: Colors.white.withOpacity(0.8),
                                    width: 2,
                                  ),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                              ),
                            ),
                            
                            // Corner highlights for alignment
                            Positioned.fill(
                              child: LayoutBuilder(
                                builder: (context, constraints) {
                                  final double cornerSize = 24.0;
                                  final double borderThickness = 4.0;
                                  final Color cornerColor = Colors.white;
                                  
                                  return Stack(
                                    children: [
                                      // Top Left Corner
                                      Positioned(
                                        top: 18,
                                        left: 18,
                                        child: Container(
                                          width: cornerSize,
                                          height: cornerSize,
                                          decoration: BoxDecoration(
                                            border: Border(
                                              top: BorderSide(color: cornerColor, width: borderThickness),
                                              left: BorderSide(color: cornerColor, width: borderThickness),
                                            ),
                                          ),
                                        ),
                                      ),
                                      // Top Right Corner
                                      Positioned(
                                        top: 18,
                                        right: 18,
                                        child: Container(
                                          width: cornerSize,
                                          height: cornerSize,
                                          decoration: BoxDecoration(
                                            border: Border(
                                              top: BorderSide(color: cornerColor, width: borderThickness),
                                              right: BorderSide(color: cornerColor, width: borderThickness),
                                            ),
                                          ),
                                        ),
                                      ),
                                      // Bottom Left Corner
                                      Positioned(
                                        bottom: 18,
                                        left: 18,
                                        child: Container(
                                          width: cornerSize,
                                          height: cornerSize,
                                          decoration: BoxDecoration(
                                            border: Border(
                                              bottom: BorderSide(color: cornerColor, width: borderThickness),
                                              left: BorderSide(color: cornerColor, width: borderThickness),
                                            ),
                                          ),
                                        ),
                                      ),
                                      // Bottom Right Corner
                                      Positioned(
                                        bottom: 18,
                                        right: 18,
                                        child: Container(
                                          width: cornerSize,
                                          height: cornerSize,
                                          decoration: BoxDecoration(
                                            border: Border(
                                              bottom: BorderSide(color: cornerColor, width: borderThickness),
                                              right: BorderSide(color: cornerColor, width: borderThickness),
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                            ),
                            
                            // Mock Grid lines if Grid is ON
                            if (scanVM.isGridOn) ...[
                              Column(
                                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                children: [
                                  Divider(color: Colors.white24, thickness: 1),
                                  Divider(color: Colors.white24, thickness: 1),
                                ],
                              ),
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                                children: [
                                  VerticalDivider(color: Colors.white24, width: 1, thickness: 1),
                                  VerticalDivider(color: Colors.white24, width: 1, thickness: 1),
                                ],
                              ),
                            ]
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                
                // Bottom Panel for Shutter controls
                Container(
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.vertical(top: Radius.circular(32)),
                    boxShadow: [
                      BoxShadow(
                        color: Color(0x0A000000),
                        blurRadius: 15,
                        offset: Offset(0, -4),
                      ),
                    ],
                  ),
                  padding: const EdgeInsets.symmetric(vertical: 24, horizontal: 40),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // Gallery Button
                      GestureDetector(
                        onTap: () async {
                          final success = await scanVM.selectImage(ImageSource.gallery);
                          if (success && context.mounted) {
                            context.push('/processing');
                          }
                        },
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: const Color(0xFFF1F5F9),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: const Icon(
                                Icons.image_outlined,
                                color: Color(0xFF475569),
                                size: 24,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Gallery',
                              style: GoogleFonts.inter(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: const Color(0xFF64748B),
                              ),
                            ),
                          ],
                        ),
                      ),
                      
                      // Shutter Button
                      GestureDetector(
                        onTap: () async {
                          final success = await scanVM.selectImage(ImageSource.camera);
                          if (success && context.mounted) {
                            context.push('/processing');
                          }
                        },
                        child: Container(
                          height: 74,
                          width: 74,
                          decoration: BoxDecoration(
                            color: Colors.white,
                            shape: BoxShape.circle,
                            border: Border.all(color: const Color(0xFFCBD5E1), width: 4),
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF2563EB).withOpacity(0.15),
                                blurRadius: 10,
                                offset: const Offset(0, 4),
                              ),
                            ],
                          ),
                          padding: const EdgeInsets.all(4),
                          child: Container(
                            decoration: const BoxDecoration(
                              color: Color(0xFF02569B),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(
                              Icons.camera_alt,
                              color: Colors.white,
                              size: 28,
                            ),
                          ),
                        ),
                      ),
                      
                      // Recent Button
                      GestureDetector(
                        onTap: () {
                          context.push('/complete');
                        },
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: const Color(0xFFF1F5F9),
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: const Icon(
                                Icons.history_toggle_off_rounded,
                                color: Color(0xFF475569),
                                size: 24,
                              ),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              'Recent',
                              style: GoogleFonts.inter(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: const Color(0xFF64748B),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
