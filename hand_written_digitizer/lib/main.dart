import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'services/api_service.dart';
import 'models/document_model.dart';
import 'views/auth/sign_in_view.dart';
import 'views/auth/sign_up_view.dart';
import 'views/home/home_view.dart';
import 'views/scan/scan_view.dart';
import 'views/scan/processing_view.dart';
import 'views/document/digitization_complete_view.dart';
import 'views/summary/summary_view.dart';
import 'views/profile/profile_view.dart';

// GoRouter configuration
GoRouter createRouter(String initialLocation) {
  return GoRouter(
    initialLocation: initialLocation,
    routes: [
      GoRoute(path: '/signIn', builder: (context, state) => const SignInView()),
      GoRoute(path: '/signUp', builder: (context, state) => const SignUpView()),
      GoRoute(path: '/home', builder: (context, state) => const HomeView()),
      GoRoute(path: '/scan', builder: (context, state) => const ScanView()),
      GoRoute(
        path: '/processing',
        builder: (context, state) => const ProcessingView(),
      ),
      GoRoute(
        path: '/complete',
        builder: (context, state) {
          final doc = state.extra as DocumentModel?;
          return DigitizationCompleteView(document: doc);
        },
      ),
      GoRoute(
        path: '/summary',
        builder: (context, state) => const SummaryView(),
      ),
      GoRoute(
        path: '/profile',
        builder: (context, state) => const ProfileView(),
      ),
    ],
  );
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Check if token exists to route accordingly
  final token = await ApiService.getToken();
  final String initialLocation = token != null ? '/home' : '/signIn';

  runApp(ProviderScope(child: MyApp(initialLocation: initialLocation)));
}

class MyApp extends StatelessWidget {
  final String initialLocation;
  const MyApp({super.key, required this.initialLocation});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Luminous Notes',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2563EB),
          primary: const Color(0xFF2563EB),
          secondary: const Color(0xFF02569B),
        ),
        useMaterial3: true,
      ),
      routerConfig: createRouter(initialLocation),
    );
  }
}
