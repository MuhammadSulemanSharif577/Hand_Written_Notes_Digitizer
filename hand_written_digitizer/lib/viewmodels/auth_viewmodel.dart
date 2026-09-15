import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';

class AuthViewModel extends ChangeNotifier {
  bool _isLoading = false;
  bool _isPasswordObscured = true;
  bool _isConfirmPasswordObscured = true;
  bool _agreeToTerms = false;
  String? _errorMessage;

  bool get isLoading => _isLoading;
  bool get isPasswordObscured => _isPasswordObscured;
  bool get isConfirmPasswordObscured => _isConfirmPasswordObscured;
  bool get agreeToTerms => _agreeToTerms;
  String? get errorMessage => _errorMessage;

  void togglePasswordObscure() {
    _isPasswordObscured = !_isPasswordObscured;
    notifyListeners();
  }

  void toggleConfirmPasswordObscure() {
    _isConfirmPasswordObscured = !_isConfirmPasswordObscured;
    notifyListeners();
  }

  void toggleAgreeToTerms(bool? value) {
    _agreeToTerms = value ?? false;
    notifyListeners();
  }

  Future<bool> signIn(String email, String password) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    final result = await ApiService.signIn(email, password);

    _isLoading = false;
    if (result['success'] == true) {
      notifyListeners();
      return true;
    } else {
      _errorMessage = result['error'];
      notifyListeners();
      return false;
    }
  }

  Future<bool> signUp(String name, String email, String password) async {
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    final result = await ApiService.signUp(name, email, password);

    if (result['success'] == true) {
      // Auto sign-in after successful registration
      final loginResult = await ApiService.signIn(email, password);
      _isLoading = false;
      if (loginResult['success'] == true) {
        notifyListeners();
        return true;
      } else {
        _errorMessage = 'Registered successfully, but failed to auto-login';
        notifyListeners();
        return true; // The user can still log in manually
      }
    } else {
      _isLoading = false;
      _errorMessage = result['error'];
      notifyListeners();
      return false;
    }
  }

  Future<void> signOut() async {
    await ApiService.clearToken();
    notifyListeners();
  }
}

// Riverpod Provider definition
final authViewModelProvider = ChangeNotifierProvider<AuthViewModel>((ref) {
  return AuthViewModel();
});
