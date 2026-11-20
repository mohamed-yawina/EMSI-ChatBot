import 'dart:typed_data';

import 'package:image_picker/image_picker.dart';

const int maxChatImageBytes = 5 * 1024 * 1024;

class SelectedChatImage {
  const SelectedChatImage({
    required this.bytes,
    required this.mimeType,
    required this.fileName,
  });

  final Uint8List bytes;
  final String mimeType;
  final String fileName;
}

abstract interface class ChatImagePicker {
  Future<SelectedChatImage?> pickImage();
}

class PlatformChatImagePicker implements ChatImagePicker {
  PlatformChatImagePicker({ImagePicker? picker})
    : _picker = picker ?? ImagePicker();

  final ImagePicker _picker;

  @override
  Future<SelectedChatImage?> pickImage() async {
    final selected = await _picker.pickImage(source: ImageSource.gallery);
    if (selected == null) return null;
    final bytes = await selected.readAsBytes();
    if (bytes.isEmpty || bytes.length > maxChatImageBytes) {
      throw const FormatException('L’image doit faire au maximum 5 Mo.');
    }
    final mime = _sniffMimeType(bytes);
    if (mime == null) {
      throw const FormatException('Formats acceptés : JPEG, PNG et WebP.');
    }
    return SelectedChatImage(
      bytes: bytes,
      mimeType: mime,
      fileName: _safeDisplayName(selected.name),
    );
  }
}

String? _sniffMimeType(Uint8List bytes) {
  if (bytes.length >= 3 &&
      bytes[0] == 0xff &&
      bytes[1] == 0xd8 &&
      bytes[2] == 0xff) {
    return 'image/jpeg';
  }
  if (bytes.length >= 8 &&
      bytes[0] == 0x89 &&
      bytes[1] == 0x50 &&
      bytes[2] == 0x4e &&
      bytes[3] == 0x47 &&
      bytes[4] == 0x0d &&
      bytes[5] == 0x0a &&
      bytes[6] == 0x1a &&
      bytes[7] == 0x0a) {
    return 'image/png';
  }
  if (bytes.length >= 12 &&
      String.fromCharCodes(bytes.sublist(0, 4)) == 'RIFF' &&
      String.fromCharCodes(bytes.sublist(8, 12)) == 'WEBP') {
    return 'image/webp';
  }
  return null;
}

String _safeDisplayName(String original) {
  final leaf = original.replaceAll('\\', '/').split('/').last;
  final safe = leaf.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');
  if (safe.isEmpty) return 'image';
  return safe.length > 80 ? safe.substring(0, 80) : safe;
}
