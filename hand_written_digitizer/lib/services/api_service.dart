import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  // Configurable base URL. We use localhost loopback together with ADB reverse forwarding.
  static const String baseUrl = 'http://192.168.104.86:8000';
  
  static Future<String?> getToken() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('auth_token');
  }

  static Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('auth_token', token);
  }

  static Future<void> clearToken() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
    await prefs.remove('user_name');
    await prefs.remove('user_email');
  }

  static Future<void> saveUserInfo(String name, String email) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('user_name', name);
    await prefs.setString('user_email', email);
  }

  static Future<Map<String, String>> getUserInfo() async {
    final prefs = await SharedPreferences.getInstance();
    return {
      'name': prefs.getString('user_name') ?? 'User',
      'email': prefs.getString('user_email') ?? '',
    };
  }

  // POST /auth/signup
  static Future<Map<String, dynamic>> signUp(String fullName, String email, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/signup'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'full_name': fullName,
          'email': email,
          'password': password,
        }),
      );
      
      final data = jsonDecode(response.body);
      if (response.statusCode == 201) {
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Registration failed'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Connection error: $e'};
    }
  }

  // POST /auth/signin
  static Future<Map<String, dynamic>> signIn(String email, String password) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/auth/signin'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'email': email,
          'password': password,
        }),
      );

      final data = jsonDecode(response.body);
      if (response.statusCode == 200) {
        final token = data['access_token'];
        final user = data['user'];
        await saveToken(token);
        await saveUserInfo(user['full_name'] ?? '', user['email']);
        return {'success': true};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Invalid credentials'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Connection error: $e'};
    }
  }

  // POST /upload
  static Future<Map<String, dynamic>> uploadImage(File imageFile) async {
    try {
      final token = await getToken();
      if (token == null) {
        return {'success': false, 'error': 'Session expired. Please sign in again.'};
      }

      var request = http.MultipartRequest('POST', Uri.parse('$baseUrl/upload'));
      request.headers['Authorization'] = 'Bearer $token';
      
      final extension = imageFile.path.split('.').last.toLowerCase();
      final mimeSubType = extension == 'png' ? 'png' : (extension == 'gif' ? 'gif' : 'jpeg');
      request.files.add(await http.MultipartFile.fromPath(
        'file', 
        imageFile.path,
        contentType: MediaType('image', mimeSubType),
      ));

      var streamedResponse = await request.send();
      var response = await http.Response.fromStream(streamedResponse);

      final data = jsonDecode(response.body);
      if (response.statusCode == 201) {
        return {'success': true, 'data': data};
      } else {
        return {'success': false, 'error': data['detail'] ?? 'Upload failed'};
      }
    } catch (e) {
      return {'success': false, 'error': 'Connection error: $e'};
    }
  }

  // GET /history
  static Future<List<dynamic>> fetchHistory() async {
    try {
      final token = await getToken();
      if (token == null) {
        return [];
      }

      final response = await http.get(
        Uri.parse('$baseUrl/history'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      if (response.statusCode == 200) {
        return jsonDecode(response.body) as List<dynamic>;
      } else {
        return [];
      }
    } catch (e) {
      return [];
    }
  }

  // DELETE /history/{id}
  static Future<Map<String, dynamic>> deleteDocument(String docId) async {
    try {
      final token = await getToken();
      if (token == null) {
        return {
          'success': false,
          'error': 'Session expired. Please sign in again.',
        };
      }

      final response = await http.delete(
        Uri.parse('$baseUrl/history/$docId'),
        headers: {'Authorization': 'Bearer $token'},
      );

      if (response.statusCode == 204) {
        return {'success': true};
      }

      var message = 'Could not delete document';
      if (response.body.isNotEmpty) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        message = data['detail']?.toString() ?? message;
      }
      return {'success': false, 'error': message};
    } catch (e) {
      return {'success': false, 'error': 'Connection error: $e'};
    }
  }

  // GET /history/{id}/export/{format}
  static Future<List<int>?> downloadExportFile(String docId, String format) async {
    try {
      final token = await getToken();
      if (token == null) {
        return null;
      }

      final response = await http.get(
        Uri.parse('$baseUrl/history/$docId/export/$format'),
        headers: {
          'Authorization': 'Bearer $token',
        },
      );

      if (response.statusCode == 200) {
        return response.bodyBytes;
      } else {
        return null;
      }
    } catch (e) {
      return null;
    }
  }
}
